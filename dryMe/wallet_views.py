"""
Owner-facing wallet API. Thin on purpose: every rule (fee, whole shillings, phone
format, one open payout, locking) lives in services.wallet.
"""
import logging
from decimal import Decimal

from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .api_errors import flatten_error_detail
from .models import Payout, Wallet, WalletTransaction
from .permissions import IsShopOwner
from .services.wallet import quote_payout, request_payout
from .services.wallet_summary import wallet_summary
from .throttles import PayoutQuoteThrottle, PayoutRequestThrottle
from .wallet_serializers import (
    PayoutRequestSerializer,
    PayoutSerializer,
    WalletTransactionSerializer,
)

logger = logging.getLogger(__name__)

OWNER_ONLY = [IsAuthenticated, IsShopOwner]


def decimals_as_strings(value):
    """
    DRF's JSON encoder turns a raw Decimal into a float (0.10 -> 0.1000000000000000055…).
    Serializer DecimalFields already send strings; this makes the hand-built responses
    (wallet summary, quote, balance after a withdrawal) send money the same way.
    """
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {key: decimals_as_strings(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [decimals_as_strings(item) for item in value]
    return value


# ===============================
# 👛 WALLET SUMMARY
# ===============================
class OwnerWalletView(APIView):
    """GET owner/wallet/ — balance, pending earnings, totals, fee table, open payout."""

    permission_classes = OWNER_ONLY

    def get(self, request):
        data = wallet_summary(request.user)
        open_payout = data.pop("open_payout")
        data["open_payout"] = PayoutSerializer(open_payout).data if open_payout else None
        return Response(decimals_as_strings(data))


# ===============================
# 📒 LEDGER
# ===============================
class OwnerWalletTransactionsView(generics.ListAPIView):
    """GET owner/wallet/transactions/ — paginated, newest first."""

    serializer_class = WalletTransactionSerializer
    permission_classes = OWNER_ONLY

    def get_queryset(self):
        return WalletTransaction.objects.filter(wallet__owner=self.request.user)


# ===============================
# 💸 PAYOUTS
# ===============================
class OwnerPayoutListCreateView(generics.ListCreateAPIView):
    """
    GET  owner/payouts/ — this owner's withdrawal history (paginated).
    POST owner/payouts/ — request a withdrawal {amount, method, destination}.
    """

    serializer_class = PayoutSerializer
    permission_classes = OWNER_ONLY

    def get_queryset(self):
        return Payout.objects.filter(owner=self.request.user)

    def get_throttles(self):
        # Only withdrawal requests are rate-limited, not browsing history.
        if self.request.method == "POST":
            return [PayoutRequestThrottle()]
        return super().get_throttles()

    def create(self, request, *args, **kwargs):
        form = PayoutRequestSerializer(data=request.data)
        if not form.is_valid():
            return Response(
                {"error": flatten_error_detail(form.errors)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payout = request_payout(request.user, **form.validated_data)
        except ValidationError as exc:
            return Response(
                {"error": flatten_error_detail(exc.detail)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(
            "Payout requested id=%s owner=%s method=%s amount=%s fee=%s net=%s",
            payout.pk, request.user.pk, payout.method, payout.amount, payout.fee, payout.net_amount,
        )

        return Response(
            {
                "payout": PayoutSerializer(payout).data,
                "balance": decimals_as_strings(Wallet.objects.get(owner=request.user).balance),
            },
            status=status.HTTP_201_CREATED,
        )


class PayoutQuoteView(APIView):
    """
    GET owner/payouts/quote/?amount=500&method=mpesa
    The fee preview for the receipt block. Same function the real request uses,
    so what the owner sees is what they'll get.
    """

    permission_classes = OWNER_ONLY
    throttle_classes = [PayoutQuoteThrottle]

    def get(self, request):
        method = request.query_params.get("method", "mpesa")
        try:
            amount, fee, net = quote_payout(request.query_params.get("amount"), method)
        except ValidationError as exc:
            return Response(
                {"error": flatten_error_detail(exc.detail)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(decimals_as_strings({"method": method, "amount": amount, "fee": fee, "net_amount": net}))