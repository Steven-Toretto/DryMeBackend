"""
Weigh-in for per-kg orders.

The flow:
  1. The customer books with an ESTIMATE (price_status = "estimate") and can't pay yet.
  2. The shop accepts the order, collects the laundry, weighs it and enters the real weight.
  3. The total is recalculated from the rate agreed at booking, and the customer is notified.
  4. If the final total is within the tolerance of the ESTIMATE (default 15%) the order becomes
     "final" and the customer can pay. If it's higher, it becomes "needs_approval": the customer
     must accept the new price (or cancel) before they can pay.
  5. The customer pays the final amount. Washing starts after payment.
  6. The weight is locked once a payment has been made (or is in progress).

Every comparison is against the booked estimate, never against the previous weigh-in, so
re-weighing can't creep the price upwards in small steps.

Tolerance: settings.WEIGH_IN_TOLERANCE (a Decimal fraction, default 0.15 = 15%).
"""
import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from ..models import Order
from .notifications import notify_after_commit, price_accepted_message, weighed_message

logger = logging.getLogger(__name__)

CENT = Decimal("0.01")
MIN_WEIGHT = Decimal("0.10")
MAX_WEIGHT = Decimal("999.99")      # Order.weight is a DecimalField(max_digits=5, decimal_places=2)
DEFAULT_TOLERANCE = Decimal("0.15")
PAYMENT_LOCKED = ("paid", "pending_payment")


# ===============================
# 🔧 HELPERS
# ===============================
def tolerance():
    """How far above the estimate the final total may be before the customer must approve it."""
    try:
        value = Decimal(str(getattr(settings, "WEIGH_IN_TOLERANCE", DEFAULT_TOLERANCE)))
    except InvalidOperation:
        return DEFAULT_TOLERANCE
    return value if value.is_finite() and value >= 0 else DEFAULT_TOLERANCE


def within_tolerance(estimated_total, final_total):
    """True when final_total is at most `tolerance` above the estimate (lower is always fine)."""
    limit = Decimal(estimated_total) * (Decimal("1") + tolerance())
    return Decimal(final_total) <= limit


def parse_weight(raw):
    """Kilograms to 2 decimals, between 0.10 and 999.99."""
    message = "Enter the weight in kg, e.g. 4.5."
    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        raise ValidationError(message) from None
    if not value.is_finite() or value <= 0:
        raise ValidationError(message)
    if value > MAX_WEIGHT:
        raise ValidationError("That's too heavy to be right. Check the number.")
    value = value.quantize(CENT, rounding=ROUND_HALF_UP)
    if value < MIN_WEIGHT:
        raise ValidationError("The minimum weight is 0.1 kg.")
    return value


def payment_block_reason(order):
    """Why this order can't be paid yet (a sentence for the customer), or None when it can."""
    if not order.is_weigh_in_order:
        return None
    if order.price_status == "estimate":
        return (
            "The shop hasn't weighed your laundry yet. You can pay once they confirm the "
            "final weight. We'll notify you."
        )
    if order.price_status == "needs_approval":
        return "The final price is higher than your estimate. Accept it first, or cancel the order."
    return None


def washing_block_reason(order, new_status):
    """Why the owner can't move this order to washing / completed yet, or None."""
    if new_status not in ("washing", "completed") or not order.is_weigh_in_order:
        return None
    if order.price_status == "estimate":
        return "Weigh the laundry first, so the customer can pay the final price."
    if order.price_status == "needs_approval":
        return "Waiting for the customer to accept the new price."
    if order.payment_status != "paid":
        return "Wait for the customer's payment before washing."
    return None


# ===============================
# ⚖️ SHOP: ENTER THE REAL WEIGHT
# ===============================
@transaction.atomic
def record_weigh_in(order_id, owner, raw_weight):
    """
    The shop enters the weighed laundry. Returns (order, within_margin).
    Allowed again before payment (to fix a typo); locked once the customer has paid or a payment
    prompt is in flight.
    """
    order = Order.objects.select_for_update().filter(pk=order_id).first()
    if order is None:
        raise NotFound("Order not found.")

    if order.shop.owner_id != owner.pk:
        raise PermissionDenied("Not allowed.")

    weight = parse_weight(raw_weight)

    if not order.is_weigh_in_order or order.service.pricing_type != "per_kg":
        raise ValidationError(
            "This order is priced per item, or was booked before weigh-ins, so there is nothing to weigh."
        )

    if order.status == "pending":
        raise ValidationError("Accept the order before weighing the laundry.")
    if order.status != "confirmed":
        raise ValidationError("This order can no longer be weighed.")

    if order.payment_status == "paid":
        raise ValidationError("The weight is locked because the customer has already paid.")
    if order.payment_status == "pending_payment":
        raise ValidationError("The weight is locked because a payment is in progress.")

    order.weight = weight
    order.total_price = order.compute_total()
    within = within_tolerance(order.estimated_total_price, order.total_price)
    order.price_status = "final" if within else "needs_approval"
    order.price_accepted_at = None
    order.weighed_at = timezone.now()
    order.save(update_fields=["weight", "total_price", "price_status", "price_accepted_at", "weighed_at"])

    notify_after_commit(
        order.user,
        "order_weighed" if within else "price_approval",
        weighed_message(order, within),
        order=order,
    )

    logger.info(
        "Weighed order=%s weight=%s total=%s estimate=%s within_margin=%s",
        order.pk, weight, order.total_price, order.estimated_total_price, within,
    )
    return order, within


# ===============================
# 👍 CUSTOMER: ACCEPT THE HIGHER PRICE
# ===============================
@transaction.atomic
def accept_final_price(order_id, customer):
    """
    The customer accepts a weighed price that's above the margin. Returns (order, changed).
    Idempotent: accepting an already-final order is a no-op, so a double tap can't error.
    """
    order = Order.objects.select_for_update().filter(pk=order_id).first()
    if order is None:
        raise NotFound("Order not found.")

    if order.user_id != customer.pk:
        raise PermissionDenied("Not allowed.")

    if order.status in ("declined", "cancelled"):
        raise ValidationError("This order is no longer active.")

    if not order.is_weigh_in_order:
        raise ValidationError("There's no price to accept on this order.")

    if order.price_status == "estimate":
        raise ValidationError("The shop hasn't weighed your laundry yet.")

    if order.price_status == "final":
        return order, False

    order.price_status = "final"
    order.price_accepted_at = timezone.now()
    order.save(update_fields=["price_status", "price_accepted_at"])

    notify_after_commit(order.shop.owner, "price_accepted", price_accepted_message(order), order=order)

    logger.info("Customer accepted final price order=%s total=%s", order.pk, order.total_price)
    return order, True