from rest_framework import serializers

from .models import Payout, WalletTransaction


class WalletTransactionSerializer(serializers.ModelSerializer):

    type_label = serializers.CharField(source="get_type_display", read_only=True)

    class Meta:
        model = WalletTransaction
        fields = (
            "id",
            "type",
            "type_label",
            "amount",          # signed: + earnings, - withdrawals
            "balance_after",
            "note",
            "order",
            "payout",
            "created_at",
        )
        read_only_fields = fields


class PayoutSerializer(serializers.ModelSerializer):
    """Output only. Nothing on a payout is ever writable through the API."""

    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Payout
        fields = (
            "id",
            "amount",          # gross — what left the wallet
            "fee",
            "net_amount",      # what the owner actually receives
            "method",
            "destination",
            "status",
            "status_label",
            "reference",
            "reject_reason",
            "requested_at",
            "reviewed_at",
            "paid_at",
        )
        read_only_fields = fields


class PayoutRequestSerializer(serializers.Serializer):
    """
    Input for POST owner/payouts/. Deliberately has no fee / net_amount / status:
    the server computes the fee, and any such keys in the body are ignored.
    Amount, phone and bank-detail rules live in services.wallet (one place).
    """

    amount = serializers.CharField(
        max_length=20,
        error_messages={
            "required": "Enter an amount.",
            "blank": "Enter an amount.",
            "null": "Enter an amount.",
        },
    )
    method = serializers.ChoiceField(
        choices=["mpesa", "bank"],
        error_messages={
            "required": "Choose how you want to be paid.",
            "invalid_choice": "Choose M-Pesa or bank.",
        },
    )
    destination = serializers.CharField(
        max_length=255,
        error_messages={
            "required": "Enter where to send the money.",
            "blank": "Enter where to send the money.",
            "null": "Enter where to send the money.",
        },
    )