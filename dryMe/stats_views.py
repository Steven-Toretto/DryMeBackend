from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import IsShopOwner
from .services.owner_stats import owner_stats


class OwnerStatsView(APIView):
    """
    GET owner/stats/ — dashboard overview numbers over ALL of this owner's orders:
    total_orders, orders_this_week (rolling 7 days), unique_customers,
    status_counts {pending, confirmed, washing, completed, declined, cancelled}, shops_count.
    """

    permission_classes = [IsAuthenticated, IsShopOwner]

    def get(self, request):
        return Response(owner_stats(request.user))