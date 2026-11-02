"""
Weigh-in endpoints. Thin on purpose: every rule lives in services.weigh_in.

POST orders/<pk>/weigh/          owner:    {"weight": "4.5"}
POST orders/<pk>/accept-price/   customer: accept a weighed price that's above the margin
"""
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .api_errors import flatten_error_detail
from .serializers import OrderSerializer
from .services.weigh_in import accept_final_price, record_weigh_in


def _error(exc):
    return Response({"error": flatten_error_detail(exc.detail)}, status=exc.status_code)


class WeighOrderView(APIView):
    """The shop enters the weighed laundry; the total is recalculated and the customer notified."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            order, within_margin = record_weigh_in(pk, request.user, request.data.get("weight"))
        except APIException as exc:
            return _error(exc)

        return Response(
            {
                "message": (
                    "Weight saved. The customer can pay now."
                    if within_margin
                    else "Weight saved. The price is above the estimate, so the customer must accept it before paying."
                ),
                "within_margin": within_margin,
                "order": OrderSerializer(order, context={"request": request}).data,
            },
            status=status.HTTP_200_OK,
        )


class AcceptPriceView(APIView):
    """The customer accepts the higher final price."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            order, _changed = accept_final_price(pk, request.user)
        except APIException as exc:
            return _error(exc)

        return Response(
            {
                "message": "Price accepted. You can pay now.",
                "order": OrderSerializer(order, context={"request": request}).data,
            },
            status=status.HTTP_200_OK,
        )