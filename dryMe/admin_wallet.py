"""
Admin for the wallet system. Import this from admin.py (see CHANGES.md).

Payouts are processed ONLY through the actions below, which call the same service
functions the tests cover (locked, idempotent, ledger-writing). Every payout field
is read-only and rows can't be added or deleted, so money can't be changed by
editing a form.

Your routine for a withdrawal:
  1. Filter by status = Requested.
  2. Optional: run "Approve" so you can see which ones you've picked up.
  3. Send the TO SEND amount (net — NOT the gross) to the destination via M-Pesa / bank.
  4. Select exactly that payout, type the M-Pesa code / bank ref in "Payment reference",
     run "Mark PAID".
  If you can't or won't pay it: type a reason, run "Reject" (or "Mark FAILED" if you
  tried and the transfer didn't go through). The FULL requested amount, fee included,
  goes back to the owner's wallet.
"""
from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm
from rest_framework.exceptions import ValidationError as ApiValidationError

from .api_errors import flatten_error_detail
from .models import Payout, Wallet, WalletTransaction
from .services.wallet import (
    approve_payout,
    fail_payout,
    ledger_total,
    mark_payout_paid,
    reject_payout,
)


# ===============================
# 💸 PAYOUTS
# ===============================
class PayoutActionForm(ActionForm):
    """Extra inputs shown next to the action dropdown on the payouts list."""

    reference = forms.CharField(
        required=False,
        label="Payment reference",
        widget=forms.TextInput(attrs={"placeholder": "M-Pesa code / bank ref  (for Mark PAID)"}),
    )
    reason = forms.CharField(
        required=False,
        label="Reason",
        widget=forms.TextInput(attrs={"placeholder": "shown in the record  (for Reject / Mark FAILED)"}),
    )


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    action_form = PayoutActionForm
    actions = ["approve_selected", "mark_paid", "reject_selected", "mark_failed"]

    list_display = (
        "id", "requested_at", "owner", "method", "destination",
        "amount", "fee", "to_send", "status", "reference",
    )
    list_filter = ("status", "method")
    list_select_related = ("owner",)
    search_fields = ("owner__email", "owner__username", "destination", "reference")
    ordering = ("-requested_at",)
    readonly_fields = [f.name for f in Payout._meta.fields]

    @admin.display(description="TO SEND (KES)", ordering="net_amount")
    def to_send(self, obj):
        return obj.net_amount

    # No manual creation or deletion: payouts are born from the API and finished by actions.
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    # ---- plumbing ----
    def _apply(self, request, queryset, fn, past_tense, **kwargs):
        done = 0
        for payout in queryset:
            try:
                fn(payout.pk, request.user, **kwargs)
                done += 1
            except ApiValidationError as exc:
                self.message_user(
                    request,
                    f"Payout #{payout.pk}: {flatten_error_detail(exc.detail)}",
                    messages.ERROR,
                )
        if done:
            self.message_user(
                request,
                f"{past_tense} {done} payout{'s' if done != 1 else ''}.",
                messages.SUCCESS,
            )

    # ---- actions ----
    @admin.action(description="Approve — I'm processing these", permissions=["change"])
    def approve_selected(self, request, queryset):
        self._apply(request, queryset, approve_payout, "Approved")

    @admin.action(
        description="Mark PAID — fill in 'Payment reference' (select exactly one)",
        permissions=["change"],
    )
    def mark_paid(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(
                request,
                "Select exactly one payout — each payment has its own reference.",
                messages.ERROR,
            )
            return
        self._apply(
            request, queryset, mark_payout_paid, "Marked paid",
            reference=request.POST.get("reference", ""),
        )

    @admin.action(
        description="Reject — fill in 'Reason' (full amount returns to the owner)",
        permissions=["change"],
    )
    def reject_selected(self, request, queryset):
        self._apply(
            request, queryset, reject_payout, "Rejected",
            reason=request.POST.get("reason", ""),
        )

    @admin.action(
        description="Mark FAILED — transfer didn't go through; fill in 'Reason'",
        permissions=["change"],
    )
    def mark_failed(self, request, queryset):
        self._apply(
            request, queryset, fail_payout, "Marked failed",
            reason=request.POST.get("reason", ""),
        )


# ===============================
# 👛 WALLETS + 📒 LEDGER (view-only)
# ===============================
class LedgerInline(admin.TabularInline):
    model = WalletTransaction
    extra = 0
    can_delete = False
    fields = ("created_at", "type", "amount", "balance_after", "order", "payout", "note")
    readonly_fields = fields
    ordering = ("-created_at", "-id")
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("owner", "balance", "ledger_matches", "updated_at")
    list_select_related = ("owner",)
    search_fields = ("owner__email", "owner__username")
    readonly_fields = ("owner", "balance", "ledger_matches", "created_at", "updated_at")
    fields = readonly_fields
    inlines = [LedgerInline]

    @admin.display(boolean=True, description="Ledger = balance")
    def ledger_matches(self, obj):
        """Integrity check: the append-only ledger must always sum to the balance."""
        return ledger_total(obj) == obj.balance

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "wallet", "type", "amount", "balance_after", "order", "payout", "note")
    list_filter = ("type",)
    list_select_related = ("wallet__owner",)
    search_fields = ("wallet__owner__email", "wallet__owner__username", "note")
    ordering = ("-created_at", "-id")

    # The ledger is append-only: look, don't touch.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False