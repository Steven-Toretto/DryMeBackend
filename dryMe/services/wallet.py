"""
Wallet & payout business logic.

Invariants this module enforces:
- Money enters a wallet ONLY via settle_order(), when an order is paid AND completed.
- Every balance change writes exactly one WalletTransaction (append-only ledger),
  so  wallet.balance == sum(ledger)  always holds (see ledger_total()).
- The payout fee is computed server-side and snapshotted on the Payout row.
- One open payout per owner (also enforced by a partial unique index).
- All mutations are atomic and row-locked (wallet / order / payout).
"""
import logging
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from ..models import Order, Payout, Wallet, WalletTransaction
from .notifications import credit_message, notify_after_commit, payout_message

logger = logging.getLogger(__name__)

CENT = Decimal("0.01")
MAX_AMOUNT = Decimal("10000000")
OPEN_STATUSES = ("requested", "approved")
_MSISDN_RE = re.compile(r"^254[17]\d{8}$")


# ===============================
# 🔧 HELPERS
# ===============================
def _money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def get_locked_wallet(owner):
    """Get-or-create the owner's wallet, then lock the row. Call inside atomic()."""
    wallet, _ = Wallet.objects.get_or_create(owner=owner)
    return Wallet.objects.select_for_update().get(pk=wallet.pk)


def _apply(wallet, tx_type, amount, *, order=None, payout=None, note=""):
    """Move the balance and write the matching ledger row. Wallet must be locked."""
    wallet.balance += amount
    wallet.save(update_fields=["balance", "updated_at"])
    return WalletTransaction.objects.create(
        wallet=wallet,
        type=tx_type,
        amount=amount,
        balance_after=wallet.balance,
        order=order,
        payout=payout,
        note=note,
    )


def ledger_total(wallet):
    """Sum of all ledger rows — must always equal wallet.balance."""
    return wallet.transactions.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")


# ===============================
# 💰 SETTLE AN ORDER INTO THE WALLET
# ===============================
@transaction.atomic
def settle_order(order_id):
    """
    Credit the shop owner's wallet (net of commission) once the order is both
    paid and completed. Safe to call from every place either condition can
    become true — it's a no-op until both hold, and a no-op after settling.
    Returns the WalletTransaction, or None if nothing was credited.
    """
    order = Order.objects.select_for_update().get(pk=order_id)

    if order.settled_at or order.status != "completed" or order.payment_status != "paid":
        return None

    # Commission is taken on what we actually received (matches the M-Pesa statement).
    gross = (
        order.amount_paid
        if order.amount_paid is not None
        else Decimal(order.payable_amount())  # legacy rows paid before amount_paid existed
    )
    commission = _money(gross * settings.COMMISSION_RATE)
    earnings = gross - commission

    wallet = get_locked_wallet(order.shop.owner)
    tx = _apply(
        wallet,
        "sale_credit",
        earnings,
        order=order,
        note=f"Order #{order.pk:05d}",
    )

    order.commission_amount = commission
    order.owner_earnings = earnings
    order.settled_at = timezone.now()
    order.save(update_fields=["commission_amount", "owner_earnings", "settled_at"])

    notify_after_commit(order.shop.owner, "wallet_credited", credit_message(order, earnings), order=order)

    logger.info("Settled order=%s gross=%s commission=%s earnings=%s", order.pk, gross, commission, earnings)
    return tx


# ===============================
# 🧾 PAYOUT: QUOTE + REQUEST
# ===============================
def normalize_msisdn(raw):
    """0712…, 0112…, +254712…, 712… → 2547XXXXXXXX / 2541XXXXXXXX, else None."""
    digits = re.sub(r"[\s\-()]", "", str(raw or ""))
    if digits.startswith("+"):
        digits = digits[1:]
    if digits.startswith("0"):
        digits = "254" + digits[1:]
    elif len(digits) == 9 and digits[:1] in ("7", "1"):
        digits = "254" + digits
    return digits if _MSISDN_RE.match(digits) else None


def _parse_amount(raw):
    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        raise ValidationError("Enter a valid amount.") from None
    if not value.is_finite() or value <= 0:
        raise ValidationError("Enter an amount greater than zero.")
    if value > MAX_AMOUNT:
        raise ValidationError("That amount is too large.")
    if value != value.to_integral_value():
        raise ValidationError("Enter a whole number of shillings.")
    return value.quantize(CENT)


def get_payout_fee(amount, method):
    """Single place to change if the fee ever becomes tiered by amount."""
    return _money(settings.PAYOUT_FEES[method])


def quote_payout(amount, method):
    """Validate and price a withdrawal. Returns (amount, fee, net). Fee is NEVER client-supplied."""
    if method not in settings.PAYOUT_FEES:
        raise ValidationError("Unsupported payout method.")
    amount = _parse_amount(amount)
    fee = get_payout_fee(amount, method)
    net = amount - fee
    if net < settings.PAYOUT_MIN_NET:
        raise ValidationError(f"Amount must be more than the KES {fee:.0f} transfer fee.")
    return amount, fee, net


def _clean_destination(method, raw):
    if method == "mpesa":
        phone = normalize_msisdn(raw)
        if not phone:
            raise ValidationError("Enter a valid Safaricom number, e.g. 0712 345 678.")
        return phone
    text = " ".join(str(raw or "").split())
    if len(text) < 10 or len(text) > 255:
        raise ValidationError("Enter the bank name, account name and account number.")
    return text


def request_payout(owner, amount, method, destination):
    """
    Owner asks to withdraw `amount`. The FULL amount leaves the wallet now
    (held); the owner receives amount - fee. One open payout at a time.
    """
    if getattr(owner, "role", None) != "owner":
        raise ValidationError("Only shop owners can withdraw.")

    amount, fee, net = quote_payout(amount, method)
    destination = _clean_destination(method, destination)

    with transaction.atomic():
        wallet = get_locked_wallet(owner)  # serialises concurrent requests per owner

        if Payout.objects.filter(owner=owner, status__in=OPEN_STATUSES).exists():
            raise ValidationError("You already have a withdrawal in progress.")

        if amount > wallet.balance:
            raise ValidationError("Insufficient balance.")

        payout = Payout.objects.create(
            owner=owner,
            amount=amount,
            fee=fee,
            net_amount=net,
            method=method,
            destination=destination,
        )
        _apply(wallet, "payout_hold", -amount, payout=payout, note=f"Withdrawal #{payout.pk}")

    return payout


# ===============================
# 🛠️ PAYOUT: ADMIN TRANSITIONS (called from Django admin actions in Step 3)
# ===============================
def _locked_payout(payout_id):
    return Payout.objects.select_for_update().get(pk=payout_id)


def _stamp_review(payout, admin_user):
    if payout.reviewed_by_id is None:
        payout.reviewed_by = admin_user
    if payout.reviewed_at is None:
        payout.reviewed_at = timezone.now()


@transaction.atomic
def approve_payout(payout_id, admin_user):
    payout = _locked_payout(payout_id)
    if payout.status != "requested":
        raise ValidationError("Only requested payouts can be approved.")
    payout.status = "approved"
    _stamp_review(payout, admin_user)
    payout.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    notify_after_commit(payout.owner, "payout_approved", payout_message("approved", payout))
    return payout


@transaction.atomic
def mark_payout_paid(payout_id, admin_user, reference):
    """You've sent the money. `reference` = M-Pesa receipt or bank ref. Balance already held — no ledger change."""
    reference = (reference or "").strip()
    if not reference:
        raise ValidationError("A payment reference (M-Pesa code or bank ref) is required.")
    payout = _locked_payout(payout_id)
    if payout.status not in OPEN_STATUSES:
        raise ValidationError("This payout is already finalised.")
    payout.status = "paid"
    payout.reference = reference
    payout.paid_at = timezone.now()
    _stamp_review(payout, admin_user)
    payout.save(update_fields=["status", "reference", "paid_at", "reviewed_by", "reviewed_at"])
    notify_after_commit(payout.owner, "payout_paid", payout_message("paid", payout))
    return payout


def _reverse_payout(payout_id, admin_user, reason, final_status):
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("A reason is required.")
    with transaction.atomic():
        payout = _locked_payout(payout_id)
        if payout.status not in OPEN_STATUSES:
            raise ValidationError("This payout is already finalised.")
        wallet = get_locked_wallet(payout.owner)
        # Nothing was sent, so the FULL gross amount (fee included) goes back.
        _apply(wallet, "payout_reversal", payout.amount, payout=payout, note=f"Withdrawal #{payout.pk} {final_status}")
        payout.status = final_status
        payout.reject_reason = reason
        _stamp_review(payout, admin_user)
        payout.save(update_fields=["status", "reject_reason", "reviewed_by", "reviewed_at"])
        notify_after_commit(payout.owner, f"payout_{final_status}", payout_message(final_status, payout, reason))
    return payout


def reject_payout(payout_id, admin_user, reason):
    return _reverse_payout(payout_id, admin_user, reason, "rejected")


def fail_payout(payout_id, admin_user, reason):
    """The transfer was attempted but didn't go through."""
    return _reverse_payout(payout_id, admin_user, reason, "failed")