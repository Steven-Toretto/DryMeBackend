"""
Read-side helpers for the owner's wallet screen. Nothing here writes.
"""
from decimal import Decimal

from django.conf import settings
from django.db.models import Sum

from ..models import Order, Payout, Wallet, WalletTransaction
from .wallet import OPEN_STATUSES, _money

ZERO = Decimal("0.00")

# Orders that are paid but whose earnings haven't reached the wallet yet.
IN_PROGRESS_STATUSES = ("pending", "confirmed", "washing")


def pending_earnings(owner):
    """
    What the owner WILL earn (after commission) from orders that are already paid
    but not completed. Computed per order with the same rounding as settle_order,
    so the number matches what actually lands in the wallet.
    """
    grosses = Order.objects.filter(
        shop__owner=owner,
        payment_status="paid",
        settled_at__isnull=True,
        status__in=IN_PROGRESS_STATUSES,
    ).values_list("amount_paid", flat=True)

    total = ZERO
    for gross in grosses:
        if gross is None:
            continue
        total += gross - _money(gross * settings.COMMISSION_RATE)
    return total


def wallet_summary(owner):
    wallet = Wallet.objects.filter(owner=owner).first()

    lifetime = (
        WalletTransaction.objects
        .filter(wallet__owner=owner, type="sale_credit")
        .aggregate(total=Sum("amount"))["total"]
    ) or ZERO

    paid = Payout.objects.filter(owner=owner, status="paid").aggregate(
        gross=Sum("amount"), fees=Sum("fee"),
    )

    return {
        "balance": wallet.balance if wallet else ZERO,            # available to withdraw now
        "pending_earnings": pending_earnings(owner),              # paid orders not yet completed
        "lifetime_earned": lifetime,
        "total_withdrawn": paid["gross"] or ZERO,                 # gross, before fees
        "total_fees_paid": paid["fees"] or ZERO,
        "commission_rate": settings.COMMISSION_RATE,
        "payout_fees": dict(settings.PAYOUT_FEES),                # for the live receipt preview
        "open_payout": Payout.objects.filter(owner=owner, status__in=OPEN_STATUSES).first(),
    }