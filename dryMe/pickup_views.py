from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .services.pickup import available_days


class PickupSlotsView(APIView):
    """
    GET pickup-slots/ — the pickup days and two-hour windows that can be booked right now (Nairobi time).
    Public: nothing here is personal, and the booking page shows it before the customer signs in.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"timezone": "Africa/Nairobi", "days": available_days()})