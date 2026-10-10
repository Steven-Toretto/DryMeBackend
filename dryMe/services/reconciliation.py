"""
Payment reconciliation — the safety net for lost or delayed webhooks.

Finds PaymentAttempts still PENDING after `min_age`, asks Safaricom (STK Query)
what happened to each, and applies the answer through payments.resolve_attempt(),
the same code path the webhook uses. That makes it safe to run alongside webhooks
and safe to run overlapping with itself: an attempt can only be resolved once.

Network calls happen OUTSIDE any DB transaction/lock; resolve_attempt() opens its
own short one, so a slow Safaricom response never holds a row lock.

What a status query can and can't tell us:
  + whether the prompt was paid (ResultCode 0) or not (any other ResultCode)
  - the M-Pesa receipt and the amount (the query returns neither). A reconciled
    payment is recorded with no receipt; if the real webhook arrives later it
    fills the receipt in (see payments._already_resolved). Otherwise take the
    receipt from your M-Pesa statement.
"""
import logging
import time
from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from .. import mpesa
from ..models import PaymentAttempt
from .payments import resolve_attempt

logger = logging.getLogger(__name__)

Status = PaymentAttempt.Status

# Daraja answers "I haven't got a final result yet" with this error code (HTTP 500).
PROCESSING_ERROR_CODE = "500.001.1001"

SUCCESS, FAILED, PROCESSING, UNKNOWN = "success", "failed", "processing", "unknown"


def interpret_query_response(data, checkout_id):
    """Map a raw STK Query response to (verdict, result_code)."""
    if not isinstance(data, dict):
        return UNKNOWN, None

    if "ResultCode" in data:
        # Never apply an answer that isn't about the prompt we asked about.
        if str(data.get("CheckoutRequestID", checkout_id)) != checkout_id:
            return UNKNOWN, None
        try:
            code = int(data["ResultCode"])
        except (TypeError, ValueError):
            return UNKNOWN, None
        return (SUCCESS if code == 0 else FAILED), code

    if str(data.get("errorCode")) == PROCESSING_ERROR_CODE:
        return PROCESSING, None

    return UNKNOWN, None


@dataclass
class ReconcileSummary:
    checked: int = 0            # attempts we asked Safaricom about
    paid: int = 0               # newly confirmed as paid
    failed: int = 0             # newly confirmed as not paid
    duplicate_payments: int = 0  # paid, but the order was already paid -> refund flagged
    orphaned_payments: int = 0   # paid, but the order is gone -> refund flagged
    already_resolved: int = 0   # a webhook got there first
    still_pending: int = 0      # Safaricom says still processing
    unrecognised: int = 0       # response we couldn't interpret (left pending)
    errors: int = 0             # query raised (network / auth / Safaricom down)
    stale: int = 0              # PENDING and older than max_age — NOT touched, needs a human
    would_pay: int = 0          # dry-run only
    would_fail: int = 0         # dry-run only
    dry_run: bool = False

    def lines(self):
        out = [f"Checked {self.checked} pending attempt(s)" + (" [DRY RUN — nothing changed]" if self.dry_run else "")]
        if self.dry_run:
            out += [f"  would mark paid:   {self.would_pay}", f"  would mark failed: {self.would_fail}"]
        else:
            out += [f"  paid:              {self.paid}", f"  failed:            {self.failed}"]
        out += [
            f"  duplicate payments (refund needed): {self.duplicate_payments}",
            f"  orphaned payments  (refund needed): {self.orphaned_payments}",
            f"  already resolved by webhook:        {self.already_resolved}",
            f"  still processing at Safaricom:      {self.still_pending}",
            f"  unrecognised responses:             {self.unrecognised}",
            f"  query errors:                       {self.errors}",
        ]
        if self.stale:
            out.append(f"  STALE pending older than the window (not touched): {self.stale}")
        return out


def _tally(summary, outcome, checkout_id):
    if outcome == "paid":
        summary.paid += 1
    elif outcome == "failed":
        summary.failed += 1
    elif outcome == "duplicate_payment":
        summary.duplicate_payments += 1
    elif outcome == "orphaned_payment":
        summary.orphaned_payments += 1
    elif outcome in ("duplicate", "receipt_backfilled"):
        summary.already_resolved += 1
    else:
        logger.error("Unexpected reconcile outcome=%s checkout=%s", outcome, checkout_id)
        summary.errors += 1


def reconcile_pending_attempts(
    *,
    min_age=timedelta(minutes=2),
    max_age=timedelta(hours=48),
    limit=50,
    sleep=1.0,
    dry_run=False,
    query_fn=None,
):
    """
    min_age  don't touch prompts younger than this — the customer may still be typing their PIN
             and the webhook normally lands within seconds.
    max_age  stop querying beyond this; older PENDING attempts are only counted as `stale`.
    limit    max Safaricom queries per run (oldest first), to stay inside rate limits.
    sleep    seconds between queries.
    query_fn injectable for tests; defaults to mpesa.stk_query.
    """
    query = query_fn or mpesa.stk_query
    now = timezone.now()
    summary = ReconcileSummary(dry_run=dry_run)

    summary.stale = PaymentAttempt.objects.filter(
        status=Status.PENDING, created_at__lt=now - max_age,
    ).count()
    if summary.stale:
        logger.warning("%s PENDING payment attempt(s) older than %s need manual review", summary.stale, max_age)

    checkout_ids = list(
        PaymentAttempt.objects
        .filter(status=Status.PENDING, created_at__lte=now - min_age, created_at__gte=now - max_age)
        .order_by("created_at")
        .values_list("checkout_request_id", flat=True)[:limit]
    )

    for index, checkout_id in enumerate(checkout_ids):
        if index and sleep > 0:
            time.sleep(sleep)

        summary.checked += 1

        try:
            data = query(checkout_id)
        except Exception:
            logger.exception("STK query failed checkout=%s", checkout_id)
            summary.errors += 1
            continue

        verdict, result_code = interpret_query_response(data, checkout_id)

        if verdict == PROCESSING:
            summary.still_pending += 1
            continue

        if verdict == UNKNOWN:
            logger.warning(
                "Unrecognised STK query response checkout=%s: %s",
                checkout_id, sorted(data)[:8] if isinstance(data, dict) else type(data).__name__,
            )
            summary.unrecognised += 1
            continue

        if dry_run:
            if verdict == SUCCESS:
                summary.would_pay += 1
            else:
                summary.would_fail += 1
            continue

        outcome = resolve_attempt(checkout_id, result_code, source="query")
        _tally(summary, outcome, checkout_id)

    logger.info("Payment reconciliation: %s", "; ".join(line.strip() for line in summary.lines()))
    return summary