"""
Notification helpers — the one place Notification rows get created.

notify()               plain create; what views.py uses (and tests patch as views.notify).
notify_after_commit()  for money logic: queued until the surrounding transaction commits, and a
                       failure here is logged, never raised — a notification problem must not be
                       able to roll back or break a payout / settlement.
"""
import logging
import re
from decimal import Decimal

from django.db import transaction

from ..models import Notification

logger = logging.getLogger(__name__)

MAX_MESSAGE = 255      # Notification.message is a CharField(255)
MAX_REASON = 120


def notify(user, notif_type, message, order=None, review=None):
    return Notification.objects.create(
        user=user,
        notif_type=notif_type,
        message=message[:MAX_MESSAGE],
        order=order,
        review=review,
    )


def notify_after_commit(user, notif_type, message, order=None, review=None):
    def send():
        try:
            notify(user, notif_type, message, order=order, review=review)
        except Exception:
            logger.exception("Couldn't create %s notification for user=%s", notif_type, getattr(user, "pk", None))

    transaction.on_commit(send)


# ===============================
# ✍️ MESSAGES
# ===============================
def kes(value):
    """KES 500 / KES 1,234.50 — cents only when present."""
    value = Decimal(value)
    return f"KES {value:,.0f}" if value == value.to_integral_value() else f"KES {value:,.2f}"


def _destination(payout):
    if payout.method == "mpesa" and re.fullmatch(r"254\d{9}", str(payout.destination)):
        local = "0" + payout.destination[3:]
        return f"{local[:4]} {local[4:7]} {local[7:]}"
    return payout.destination


def _short(reason):
    reason = " ".join(str(reason or "").split())
    return reason if len(reason) <= MAX_REASON else reason[: MAX_REASON - 1] + "…"


def payout_message(kind, payout, reason=""):
    """kind: approved | paid | rejected | failed"""
    if kind == "approved":
        return f"Your withdrawal of {kes(payout.amount)} was approved. {kes(payout.net_amount)} is on its way to {_destination(payout)}."
    if kind == "paid":
        ref = f" Reference: {payout.reference}." if payout.reference else ""
        return f"{kes(payout.net_amount)} was sent to {_destination(payout)}.{ref}"
    if kind == "rejected":
        return f"Your withdrawal of {kes(payout.amount)} wasn't paid: {_short(reason)}. The full amount is back in your wallet."
    if kind == "failed":
        return f"Your withdrawal of {kes(payout.amount)} couldn't be completed: {_short(reason)}. The full amount is back in your wallet."
    raise ValueError(f"Unknown payout message kind: {kind}")


def credit_message(order, earnings):
    return f"Order #{order.pk:05d} completed — {kes(earnings)} added to your wallet."


def kg(value):
    """4.50 -> "4.5 kg", 10.00 -> "10 kg" (Decimal's own formatting would keep the trailing zero)."""
    return f"{format(Decimal(value).normalize(), 'f')} kg"


def weighed_message(order, within_margin):
    """Customer: the shop weighed the laundry. Say whether they can pay or must approve first."""
    shop = order.shop.name
    weight = kg(order.weight)
    if within_margin:
        return f"{shop} weighed your laundry: {weight}. Final price {kes(order.total_price)} — you can pay now."
    return (
        f"{shop} weighed your laundry at {weight}. The price is now {kes(order.total_price)}, "
        f"up from your {kes(order.estimated_total_price)} estimate. Accept it to pay, or cancel the order."
    )


def price_accepted_message(order):
    """Owner: the customer accepted the higher final price."""
    return (
        f"{order.user.username} accepted the final price of {kes(order.total_price)} "
        f"for order #{order.pk:05d}. Start washing once they've paid."
    )


