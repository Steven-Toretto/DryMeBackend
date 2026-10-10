"""
M-Pesa STK callback processing.

Kept out of the view so it's testable and the view stays a thin, authenticated
shell. Returns a short outcome string (used by tests and logs).

Defences in here:
- unknown / malformed payloads are ignored (never raise to Safaricom)
- idempotent: a replayed success for an already-paid order does nothing
- the paid Amount must equal what we asked for (Order.payable_amount())
- order row is locked so it can't race with status/decline/cancel updates
- successful payments we can't match are logged loudly for manual reconciliation
"""
import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction

from ..models import Order
from .wallet import settle_order

logger = logging.getLogger(__name__)


def _items(callback):
    meta = (callback.get("CallbackMetadata") or {}).get("Item") or []
    return {i.get("Name"): i.get("Value") for i in meta if isinstance(i, dict)}


def process_stk_callback(payload):
    try:
        callback = payload["Body"]["stkCallback"]
        if not isinstance(callback, dict):
            raise TypeError("stkCallback is not an object")
        checkout_id = str(callback["CheckoutRequestID"])
        result_code = int(callback["ResultCode"])
    except (KeyError, TypeError, ValueError):
        logger.warning("Malformed M-Pesa callback ignored")
        return "malformed"

    items = _items(callback)

    with transaction.atomic():
        order = (
            Order.objects.select_for_update()
            .filter(mpesa_checkout_request_id=checkout_id)
            .first()
        )

        if order is None:
            if result_code == 0:
                logger.error(
                    "UNMATCHED successful M-Pesa payment checkout=%s receipt=%s amount=%s — reconcile manually",
                    checkout_id, items.get("MpesaReceiptNumber"), items.get("Amount"),
                )
            return "unknown_order"

        if order.payment_status == "paid":
            return "duplicate"

        # ❌ Failed / cancelled / timed out
        if result_code != 0:
            if order.payment_status == "pending_payment":
                order.payment_status = "failed"
                order.save(update_fields=["payment_status"])
            return "failed"

        # ✅ Success — validate before trusting it
        try:
            amount = Decimal(str(items["Amount"]))
            receipt = str(items["MpesaReceiptNumber"]).strip()
        except (KeyError, InvalidOperation):
            receipt = ""
            amount = None

        if amount is None or not receipt:
            logger.error("M-Pesa success callback missing Amount/receipt order=%s checkout=%s", order.pk, checkout_id)
            return "bad_metadata"

        if amount != Decimal(order.payable_amount()):
            logger.error(
                "M-Pesa amount mismatch order=%s expected=%s got=%s receipt=%s — left unpaid",
                order.pk, order.payable_amount(), amount, receipt,
            )
            return "amount_mismatch"

        order.payment_status = "paid"
        order.mpesa_transaction_code = receipt
        order.amount_paid = amount

        # Paid after the order was already declined/cancelled → owe a refund.
        if order.status in ("declined", "cancelled"):
            order.refund_needed = True

        order.save(update_fields=["payment_status", "mpesa_transaction_code", "amount_paid", "refund_needed"])

        # No-op unless the order is already completed.
        settle_order(order.pk)

    return "paid"