"""
M-Pesa payment resolution — attempt-based, shared by webhooks and reconciliation.

Every STK prompt is one PaymentAttempt keyed by its unique CheckoutRequestID.
There are two ways an attempt learns its fate, and both go through
resolve_attempt() so they behave identically (idempotent, locked, same refunds):

  process_stk_callback()   Safaricom's webhook   (has Amount + receipt)
  reconciliation job       Daraja STK Query      (has only the result code)

Lock order is always  attempt -> order -> wallet  (settle_order takes the
wallet lock), so concurrent resolutions can't deadlock.

Outcomes returned (used by tests, logs and the reconcile summary):
  paid               attempt succeeded, order marked paid
  duplicate          this attempt was already resolved
  receipt_backfilled a late webhook supplied the receipt a status query couldn't
  duplicate_payment  a SECOND attempt succeeded for an already-paid order -> flagged for refund
  orphaned_payment   attempt succeeded but its order no longer exists -> flagged for refund
  failed             attempt failed / cancelled / timed out
  amount_mismatch    webhook Amount != the amount we asked for; left PENDING for manual review
  bad_metadata       success webhook without Amount / receipt
  unknown_attempt    no attempt with that CheckoutRequestID
  malformed          payload isn't a valid STK callback
"""
import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction

from ..models import Order, PaymentAttempt
from .wallet import settle_order

logger = logging.getLogger(__name__)

Status = PaymentAttempt.Status


def _items(callback):
    meta = (callback.get("CallbackMetadata") or {}).get("Item") or []
    return {i.get("Name"): i.get("Value") for i in meta if isinstance(i, dict)}


def _fail_order_if_nothing_pending(order_id):
    """An order only becomes 'failed' once NO other prompt for it is still in flight."""
    order = Order.objects.select_for_update().get(pk=order_id)
    if (
        order.payment_status == "pending_payment"
        and not order.payment_attempts.filter(status=Status.PENDING).exists()
    ):
        order.payment_status = "failed"
        order.save(update_fields=["payment_status"])


def _already_resolved(attempt, result_code, amount, receipt, source):
    """The attempt isn't PENDING any more. Normally that's a plain replay."""
    # Exception: reconciliation can confirm a payment but never learns the M-Pesa
    # receipt. If the real webhook turns up later, keep its receipt.
    if (
        source == "callback"
        and result_code == 0
        and receipt
        and attempt.status == Status.SUCCESSFUL
        and not attempt.transaction_code
        and not attempt.refund_needed        # i.e. this was the attempt that settled the order
        and amount == attempt.amount
    ):
        attempt.transaction_code = receipt
        attempt.save(update_fields=["transaction_code", "updated_at"])
        if attempt.order_id:
            Order.objects.filter(
                pk=attempt.order_id, mpesa_transaction_code__isnull=True,
            ).update(mpesa_transaction_code=receipt)
        return "receipt_backfilled"
    return "duplicate"


def resolve_attempt(checkout_id, result_code, *, amount=None, receipt=None, source="callback"):
    """
    Apply a final result (0 = paid, anything else = not paid) to the attempt with this
    CheckoutRequestID. `source` is "callback" (amount + receipt required and verified)
    or "query" (Daraja's status query, which returns neither — the amount is taken from
    the attempt itself, since that's exactly what the prompt asked for).
    """
    with transaction.atomic():
        # 1) Resolve the exact attempt (and lock it)
        attempt = (
            PaymentAttempt.objects.select_for_update()
            .filter(checkout_request_id=checkout_id)
            .first()
        )

        if attempt is None:
            if result_code == 0:
                logger.error(
                    "UNMATCHED successful M-Pesa payment (%s) checkout=%s receipt=%s amount=%s — reconcile manually",
                    source, checkout_id, receipt, amount,
                )
            return "unknown_attempt"

        # Idempotency: each attempt is resolved exactly once
        if attempt.status != Status.PENDING:
            return _already_resolved(attempt, result_code, amount, receipt, source)

        # 2) ❌ Failed / cancelled / timed out
        if result_code != 0:
            attempt.status = Status.FAILED
            attempt.save(update_fields=["status", "updated_at"])
            if attempt.order_id:
                _fail_order_if_nothing_pending(attempt.order_id)
            return "failed"

        # 3) ✅ Success — validate before trusting it
        if source == "callback":
            if amount is None or not receipt:
                logger.error("M-Pesa success callback missing Amount/receipt attempt=%s checkout=%s", attempt.pk, checkout_id)
                return "bad_metadata"

            if amount != attempt.amount:
                logger.error(
                    "M-Pesa amount mismatch attempt=%s expected=%s got=%s receipt=%s — left pending",
                    attempt.pk, attempt.amount, amount, receipt,
                )
                return "amount_mismatch"
        else:
            amount = attempt.amount
            receipt = receipt or None

        attempt.status = Status.SUCCESSFUL
        attempt.transaction_code = receipt

        # The order was deleted after the prompt was sent — we hold the customer's money.
        if attempt.order_id is None:
            attempt.refund_needed = True
            attempt.save(update_fields=["status", "transaction_code", "refund_needed", "updated_at"])
            logger.error(
                "ORPHANED payment (%s) attempt=%s receipt=%s amount=%s — order deleted, refund needed",
                source, attempt.pk, receipt, amount,
            )
            return "orphaned_payment"

        # 4) Lock the parent order, then mark it paid
        order = Order.objects.select_for_update().get(pk=attempt.order_id)

        if order.payment_status == "paid":
            # Double tap: the customer paid twice. Keep the record, flag the extra payment.
            attempt.refund_needed = True
            attempt.save(update_fields=["status", "transaction_code", "refund_needed", "updated_at"])
            logger.error(
                "DUPLICATE PAYMENT (%s) order=%s attempt=%s receipt=%s amount=%s — refund needed",
                source, order.pk, attempt.pk, receipt, amount,
            )
            return "duplicate_payment"

        order.payment_status = "paid"
        order.mpesa_transaction_code = receipt   # receipt of the payment that settled the order
        order.amount_paid = amount

        # Paid after the order was already declined/cancelled → owe a refund.
        if order.status in ("declined", "cancelled"):
            order.refund_needed = True

        order.save(update_fields=["payment_status", "mpesa_transaction_code", "amount_paid", "refund_needed"])
        attempt.save(update_fields=["status", "transaction_code", "updated_at"])

        logger.info("Order=%s paid via attempt=%s (%s)", order.pk, attempt.pk, source)

        # No-op unless the order is already completed.
        settle_order(order.pk)

    return "paid"


def process_stk_callback(payload):
    """Parse Safaricom's webhook body and resolve the attempt it belongs to."""
    try:
        callback = payload["Body"]["stkCallback"]
        if not isinstance(callback, dict):
            raise TypeError("stkCallback is not an object")
        checkout_id = str(callback["CheckoutRequestID"])
        result_code = int(callback["ResultCode"])
    except (KeyError, TypeError, ValueError):
        logger.warning("Malformed M-Pesa callback ignored")
        return "malformed"

    amount = receipt = None
    if result_code == 0:
        items = _items(callback)
        try:
            amount = Decimal(str(items["Amount"]))
            receipt = str(items["MpesaReceiptNumber"]).strip()[:50] or None
        except (KeyError, InvalidOperation):
            pass  # resolve_attempt reports "bad_metadata"

    return resolve_attempt(checkout_id, result_code, amount=amount, receipt=receipt, source="callback")