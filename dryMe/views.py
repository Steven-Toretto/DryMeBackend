from rest_framework import generics, permissions, parsers, status
from rest_framework.permissions import (
    IsAuthenticated,
    AllowAny
)
from rest_framework.decorators import (
    api_view,
    permission_classes
)
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import (
    RefreshToken
)
from django.contrib.auth import authenticate
import random

from .models import Order, Shop, Service
from .serializers import (
    ShopSerializer,
    ServiceSerializer,
    OrderSerializer,
    RegisterSerializer
)

# ===============================
# 🔐 REGISTER
# ===============================
class RegisterView(APIView):

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):

        serializer = RegisterSerializer(
            data=request.data
        )

        if serializer.is_valid():

            serializer.save()

            return Response(
                {"message": "User created"},
                status=status.HTTP_201_CREATED
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


# ===============================
# 🔐 LOGIN
# ===============================
class LoginView(APIView):

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):

        email = request.data.get("email", "").strip().lower()
        password = request.data.get("password")

        if not email or not password:
            return Response(
                {"error": "Email and password are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Look up user by email, then authenticate by username
        from django.contrib.auth import get_user_model
        User = get_user_model()

        try:
            user_obj = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response(
                {"error": "Invalid email or password"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # USERNAME_FIELD is now "email", so authenticate expects email=
        user = authenticate(
            request=request,
            email=user_obj.email,
            password=password
        )

        if user is None:
            return Response(
                {"error": "Invalid email or password"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        refresh = RefreshToken.for_user(
            user
        )

        return Response({
            "access": str(
                refresh.access_token
            ),
            "refresh": str(refresh),
            "role": getattr(
                user,
                "role",
                "customer"
            ),
            "username": user.username
        })


# ===============================
# 🏪 SHOPS (LIST + CREATE)
# ===============================
class ShopListCreateView(
    generics.ListCreateAPIView
):

    serializer_class = ShopSerializer
    permission_classes = [
        IsAuthenticated
    ]

    parser_classes = (
        parsers.MultiPartParser,
        parsers.FormParser,
    )

    # =========================
    # GET SHOPS
    # =========================
    def get_queryset(self):

        user = self.request.user

        if not user.is_authenticated:
            return Shop.objects.none()

        role = getattr(
            user,
            "role",
            "customer"
        )

        # OWNERS SEE THEIR SHOPS
        if role == "owner":

            return Shop.objects.filter(
                owner=user
            ).order_by("-id")

        # CUSTOMERS SEE ALL SHOPS
        return Shop.objects.all().order_by(
            "-id"
        )

    # =========================
    # SERIALIZER CONTEXT
    # =========================
    def get_serializer_context(self):

        return {
            "request": self.request
        }

    # =========================
    # CREATE SHOP
    # =========================
    def create(
        self,
        request,
        *args,
        **kwargs
    ):

        serializer = self.get_serializer(
            data=request.data
        )

        if serializer.is_valid():

            serializer.save(
                owner=request.user
            )

            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED
            )

        print(serializer.errors)

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


# ===============================
# 🏪 SHOP DETAIL
# ===============================
class ShopDetailView(
    generics.RetrieveUpdateDestroyAPIView
):

    serializer_class = ShopSerializer
    permission_classes = [
        IsAuthenticated
    ]

    queryset = Shop.objects.all()

    parser_classes = [
        parsers.MultiPartParser,
        parsers.FormParser,
    ]

    # =========================
    # SERIALIZER CONTEXT
    # =========================
    def get_serializer_context(self):

        return {
            "request": self.request
        }

    # =========================
    # UPDATE SHOP
    # =========================
    def update(
        self,
        request,
        *args,
        **kwargs
    ):

        shop = self.get_object()

        # ONLY OWNER CAN EDIT
        if shop.owner != request.user:

            return Response(
                {"error": "Not allowed"},
                status=status.HTTP_403_FORBIDDEN
            )

        # ✅ Always use partial=True so PATCH/PUT never wipes
        # fields that are not included in the request (e.g. image)
        partial = kwargs.pop("partial", True)

        serializer = self.get_serializer(
            shop,
            data=request.data,
            partial=partial
        )

        if serializer.is_valid():

            serializer.save()

            return Response(
                serializer.data
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

    # =========================
    # DELETE SHOP
    # =========================
    def destroy(
        self,
        request,
        *args,
        **kwargs
    ):

        shop = self.get_object()

        if shop.owner != request.user:

            return Response(
                {"error": "Not allowed"},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().destroy(
            request,
            *args,
            **kwargs
        )


# ===============================
# ⭐ FEATURED SHOPS (PUBLIC)
# ===============================
@api_view(["GET"])
@permission_classes([AllowAny])
def featured_shops(request):

    shops = list(
        Shop.objects.select_related(
            "owner"
        ).all()
    )

    random.shuffle(shops)

    unique_shops = []
    owners_seen = set()

    for shop in shops:

        if shop.owner.id not in owners_seen:

            unique_shops.append(shop)

            owners_seen.add(
                shop.owner.id
            )

        if len(unique_shops) == 4:
            break

    serializer = ShopSerializer(
        unique_shops,
        many=True,
        context={"request": request}
    )

    return Response(serializer.data)


# ===============================
# 🧺 SERVICES
# ===============================
class ServiceListCreateView(
    generics.ListCreateAPIView
):

    serializer_class = ServiceSerializer

    def get_queryset(self):

        queryset = Service.objects.all()

        shop_id = self.request.query_params.get(
            "shop"
        )

        if shop_id:

            queryset = queryset.filter(
                shop_id=shop_id
            )

        return queryset

    def get_permissions(self):

        if self.request.method == "POST":

            return [IsAuthenticated()]

        return [AllowAny()]

    def perform_create(
        self,
        serializer
    ):

        shop_id = self.request.data.get(
            "shop"
        )

        try:

            shop = Shop.objects.get(
                id=shop_id,
                owner=self.request.user
            )

        except Shop.DoesNotExist:

            raise permissions.PermissionDenied(
                "You do not own this shop"
            )

        serializer.save(shop=shop)


# ===============================
# 📦 ORDERS (CUSTOMER)
# ===============================
class OrderListCreateView(
    generics.ListCreateAPIView
):

    serializer_class = OrderSerializer
    permission_classes = [
        IsAuthenticated
    ]

    # =========================
    # GET CUSTOMER ORDERS
    # =========================
    def get_queryset(self):

        return Order.objects.filter(
            user=self.request.user,
            customer_archived=False
        ).order_by("-created_at")

    # =========================
    # CREATE ORDER
    # =========================
    def perform_create(
        self,
        serializer
    ):

        serializer.save(
            user=self.request.user
        )


# ===============================
# 🧑‍🔧 OWNER ORDERS
# ===============================
class OwnerOrderListView(
    generics.ListAPIView
):

    serializer_class = OrderSerializer
    permission_classes = [
        IsAuthenticated
    ]

    def get_queryset(self):

        user = self.request.user

        role = getattr(
            user,
            "role",
            "customer"
        )

        if role != "owner":

            raise permissions.PermissionDenied(
                "Only owners can view this"
            )

        return Order.objects.filter(
            shop__owner=user,
            owner_archived=False
        ).order_by("-created_at")


# ===============================
# 🔄 UPDATE ORDER STATUS
# ===============================
class UpdateOrderStatusView(
    generics.UpdateAPIView
):

    serializer_class = OrderSerializer
    permission_classes = [
        IsAuthenticated
    ]

    queryset = Order.objects.all()

    def update(
        self,
        request,
        *args,
        **kwargs
    ):

        order = self.get_object()

        # ONLY SHOP OWNER
        if order.shop.owner != request.user:

            return Response(
                {"error": "Not allowed"},
                status=status.HTTP_403_FORBIDDEN
            )

        new_status = request.data.get(
            "status"
        )

        valid_statuses = [
            "pending",
            "washing",
            "completed"
        ]

        if new_status not in valid_statuses:

            return Response(
                {"error": "Invalid status"},
                status=status.HTTP_400_BAD_REQUEST
            )

        order.status = new_status
        order.save()

        return Response({
            "message":
            "Order status updated"
        })


# ===============================
# 📁 ARCHIVE ORDER
# ===============================
class ArchiveOrderView(APIView):

    permission_classes = [
        IsAuthenticated
    ]

    def put(self, request, pk):

        try:

            order = Order.objects.get(
                id=pk
            )

        except Order.DoesNotExist:

            return Response(
                {"error": "Order not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # ONLY COMPLETED ORDERS
        if order.status != "completed":

            return Response(
                {
                    "error":
                    "Only completed orders can be archived"
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # CUSTOMER ARCHIVE
        if order.user == request.user:

            if order.customer_archived:

                return Response(
                    {
                        "error":
                        "Order already archived"
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            order.customer_archived = True
            order.save()

            return Response({
                "message":
                "Customer archived order"
            })

        # OWNER ARCHIVE
        if order.shop.owner == request.user:

            if order.owner_archived:

                return Response(
                    {
                        "error":
                        "Order already archived"
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            order.owner_archived = True
            order.save()

            return Response({
                "message":
                "Owner archived order"
            })

        return Response(
            {"error": "Not allowed"},
            status=status.HTTP_403_FORBIDDEN
        )


# ===============================
# 📁 ARCHIVED ORDERS
# ===============================
class ArchivedOrdersView(
    generics.ListAPIView
):

    serializer_class = OrderSerializer
    permission_classes = [
        IsAuthenticated
    ]

    def get_queryset(self):

        user = self.request.user

        # CUSTOMER ARCHIVES
        if user.role == "customer":

            return Order.objects.filter(
                user=user,
                customer_archived=True
            ).order_by("-created_at")

        # OWNER ARCHIVES
        if user.role == "owner":

            return Order.objects.filter(
                shop__owner=user,
                owner_archived=True
            ).order_by("-created_at")

        return Order.objects.none()

