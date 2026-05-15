from rest_framework import generics, permissions
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
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
        serializer = RegisterSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response({"message": "User created"}, status=201)

        return Response(serializer.errors, status=400)


# ===============================
# 🔐 LOGIN
# ===============================
class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")

        user = authenticate(username=username, password=password)

        if user is None:
            return Response({"error": "Invalid credentials"}, status=401)

        refresh = RefreshToken.for_user(user)

        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "role": getattr(user, "role", "customer"),
            "username": user.username
        })


# ===============================
# 🏪 SHOPS (LIST + CREATE)
# ===============================
class ShopListCreateView(generics.ListCreateAPIView):
    serializer_class = ShopSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        # FIX: prevent AnonymousUser crash
        if not user or not user.is_authenticated:
            return Shop.objects.none()

        role = getattr(user, "role", "customer")

        if role == "owner":
            return Shop.objects.filter(owner=user)

        return Shop.objects.all()

    def get_serializer_context(self):
        return {"request": self.request}

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


# ===============================
# 🏪 SHOP DETAIL
# ===============================
class ShopDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ShopSerializer
    permission_classes = [IsAuthenticated]
    queryset = Shop.objects.all()

    def get_serializer_context(self):
        return {"request": self.request}

    def update(self, request, *args, **kwargs):
        shop = self.get_object()

        if shop.owner != request.user:
            return Response({"error": "Not allowed"}, status=403)

        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        shop = self.get_object()

        if shop.owner != request.user:
            return Response({"error": "Not allowed"}, status=403)

        return super().destroy(request, *args, **kwargs)


# ===============================
# ⭐ FEATURED SHOPS (PUBLIC)
# ===============================
@api_view(['GET'])
@permission_classes([AllowAny])
def featured_shops(request):
    shops = list(Shop.objects.select_related('owner').all())
    random.shuffle(shops)

    unique_shops = []
    owners_seen = set()

    for shop in shops:
        if shop.owner.id not in owners_seen:
            unique_shops.append(shop)
            owners_seen.add(shop.owner.id)

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
class ServiceListCreateView(generics.ListCreateAPIView):
    serializer_class = ServiceSerializer

    def get_queryset(self):
        queryset = Service.objects.all()
        shop_id = self.request.query_params.get("shop")

        if shop_id:
            queryset = queryset.filter(shop_id=shop_id)

        return queryset

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated()]
        return [AllowAny()]

    def perform_create(self, serializer):
        shop_id = self.request.data.get("shop")

        try:
            shop = Shop.objects.get(id=shop_id, owner=self.request.user)
        except Shop.DoesNotExist:
            raise permissions.PermissionDenied("You do not own this shop")

        serializer.save(shop=shop)


# ===============================
# 📦 ORDERS (CUSTOMER)
# ===============================
class OrderListCreateView(generics.ListCreateAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


# ===============================
# 🧑‍🔧 OWNER ORDERS
# ===============================
class OwnerOrderListView(generics.ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, "role", "customer")

        if role != "owner":
            raise permissions.PermissionDenied("Only owners can view this")

        return Order.objects.filter(shop__owner=user)


# ===============================
# 🔄 UPDATE ORDER STATUS
# ===============================
class UpdateOrderStatusView(generics.UpdateAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    queryset = Order.objects.all()

    def update(self, request, *args, **kwargs):
        order = self.get_object()

        if order.shop.owner != request.user:
            return Response({"error": "Not allowed"}, status=403)

        order.status = request.data.get("status")
        order.save()

        return Response({"message": "Updated"})





# from rest_framework import generics, permissions, status
# from rest_framework.permissions import IsAuthenticated, AllowAny
# from rest_framework.response import Response
# from rest_framework.views import APIView
# from rest_framework_simplejwt.tokens import RefreshToken
# from django.contrib.auth import authenticate
# import random

# from rest_framework.decorators import api_view

# from .models import Order, Shop, Service
# from .serializers import (
#     ShopSerializer,
#     ServiceSerializer,
#     OrderSerializer,
#     RegisterSerializer
# )


# # ===============================
# # 🔐 REGISTER
# # ===============================
# class RegisterView(APIView):
#     permission_classes = [AllowAny]
#     authentication_classes = []

#     def post(self, request):
#         serializer = RegisterSerializer(data=request.data)

#         if serializer.is_valid():
#             serializer.save()
#             return Response({"message": "User created"}, status=201)

#         return Response(serializer.errors, status=400)


# # ===============================
# # 🔐 LOGIN
# # ===============================
# from rest_framework.views import APIView
# from rest_framework.response import Response
# from rest_framework.permissions import AllowAny
# from django.contrib.auth import authenticate
# from rest_framework_simplejwt.tokens import RefreshToken


# class LoginView(APIView):
#     permission_classes = [AllowAny]
#     authentication_classes = []

#     def post(self, request):
#         username = request.data.get("username")
#         password = request.data.get("password")

#         user = authenticate(username=username, password=password)

#         if user is None:
#             return Response({"error": "Invalid credentials"}, status=401)

#         refresh = RefreshToken.for_user(user)

#         return Response({
#             "access": str(refresh.access_token),
#             "refresh": str(refresh),
#             "role": getattr(user, "role", "customer"),  # ✅ ensures role always exists
#             "username": user.username                  # ✅ FIXED (closed properly)
#         })


# class ShopListCreateView(generics.ListCreateAPIView):

#     serializer_class = ShopSerializer
#     permission_classes = [IsAuthenticated]

#     def get_queryset(self):

#         user = self.request.user

#         if user.role == "owner":
#             return Shop.objects.filter(owner=user)

#         return Shop.objects.all()

#     def get_serializer_context(self):

#         context = super().get_serializer_context()

#         context["request"] = self.request

#         return context

#     def perform_create(self, serializer):

#         serializer.save(owner=self.request.user)

# # # ===============================
# # # 🏪 SHOPS (LIST + CREATE)
# # # ===============================
# # class ShopListCreateView(generics.ListCreateAPIView):
# #     serializer_class = ShopSerializer
# #     permission_classes = [IsAuthenticated]

# #     def get_queryset(self):
# #         user = self.request.user

# #         if user.role == "owner":
# #             return Shop.objects.filter(owner=user)

# #         return Shop.objects.all()

# #     def perform_create(self, serializer):
# #         serializer.save(owner=self.request.user)


# class ShopDetailView(generics.RetrieveUpdateDestroyAPIView):

#     serializer_class = ShopSerializer
#     permission_classes = [IsAuthenticated]
#     queryset = Shop.objects.all()

#     def get_serializer_context(self):

#         context = super().get_serializer_context()

#         context["request"] = self.request

#         return context

#     def update(self, request, *args, **kwargs):

#         shop = self.get_object()

#         if shop.owner != request.user:
#             return Response(
#                 {"error": "Not allowed"},
#                 status=403
#             )

#         return super().update(request, *args, **kwargs)

#     def destroy(self, request, *args, **kwargs):

#         shop = self.get_object()

#         if shop.owner != request.user:
#             return Response(
#                 {"error": "Not allowed"},
#                 status=403
#             )

#         return super().destroy(request, *args, **kwargs)

# # # ===============================
# # # ✏️ DELETE + UPDATE SHOP (OWNER ONLY)
# # # ===============================
# # class ShopDetailView(generics.RetrieveUpdateDestroyAPIView):
# #     serializer_class = ShopSerializer
# #     permission_classes = [IsAuthenticated]
# #     queryset = Shop.objects.all()

# #     def update(self, request, *args, **kwargs):
# #         shop = self.get_object()

# #         if shop.owner != request.user:
# #             return Response({"error": "Not allowed"}, status=403)

# #         return super().update(request, *args, **kwargs)

# #     def destroy(self, request, *args, **kwargs):
# #         shop = self.get_object()

# #         if shop.owner != request.user:
# #             return Response({"error": "Not allowed"}, status=403)

# #         return super().destroy(request, *args, **kwargs)


# # ===============================
# # ⭐ FEATURED SHOPS
# # ===============================
# @api_view(['GET'])
# def featured_shops(request):
#     shops = list(Shop.objects.select_related('owner').all())
#     random.shuffle(shops)

#     unique_shops = []
#     owners_seen = set()

#     for shop in shops:
#         if shop.owner.id not in owners_seen:
#             unique_shops.append(shop)
#             owners_seen.add(shop.owner.id)

#         if len(unique_shops) == 4:
#             break

#     serializer = ShopSerializer(unique_shops, many=True, context={"request": request})
#     return Response(serializer.data)


# # ===============================
# # 🧺 SERVICES
# # ===============================
# class ServiceListCreateView(generics.ListCreateAPIView):
#     serializer_class = ServiceSerializer

#     def get_queryset(self):
#         queryset = Service.objects.all()
#         shop_id = self.request.query_params.get("shop")

#         if shop_id:
#             queryset = queryset.filter(shop_id=shop_id)

#         return queryset

#     def get_permissions(self):
#         if self.request.method == "POST":
#             return [IsAuthenticated()]
#         return [AllowAny()]

#     def perform_create(self, serializer):
#         shop_id = self.request.data.get("shop")

#         try:
#             shop = Shop.objects.get(id=shop_id, owner=self.request.user)
#         except Shop.DoesNotExist:
#             raise permissions.PermissionDenied("You do not own this shop")

#         serializer.save(shop=shop)


# # ===============================
# # 📦 CUSTOMER ORDERS
# # ===============================
# class OrderListCreateView(generics.ListCreateAPIView):
#     serializer_class = OrderSerializer
#     permission_classes = [IsAuthenticated]

#     def get_queryset(self):
#         return Order.objects.filter(user=self.request.user)

#     def perform_create(self, serializer):
#         serializer.save(user=self.request.user)


# # ===============================
# # 🧑‍🔧 OWNER ORDERS
# # ===============================
# class OwnerOrderListView(generics.ListAPIView):
#     serializer_class = OrderSerializer
#     permission_classes = [IsAuthenticated]

#     def get_queryset(self):
#         user = self.request.user

#         if user.role != "owner":
#             raise permissions.PermissionDenied("Only owners can view this")

#         return Order.objects.filter(shop__owner=user)


# # ===============================
# # 🔄 UPDATE ORDER STATUS
# # ===============================
# class UpdateOrderStatusView(generics.UpdateAPIView):
#     serializer_class = OrderSerializer
#     permission_classes = [IsAuthenticated]
#     queryset = Order.objects.all()

#     def update(self, request, *args, **kwargs):
#         order = self.get_object()

#         if order.shop.owner != request.user:
#             return Response({"error": "Not allowed"}, status=403)

#         order.status = request.data.get("status")
#         order.save()

#         return Response({"message": "Updated"})












# 


# from rest_framework import generics, permissions, status
# from rest_framework.permissions import IsAuthenticated, AllowAny
# from rest_framework.response import Response
# from rest_framework.views import APIView
# from rest_framework_simplejwt.tokens import RefreshToken
# from django.contrib.auth import authenticate
# from django.utils.timezone import now
# from datetime import timedelta
# import random

# from rest_framework.decorators import api_view

# from .models import Order, Shop, Service
# from .serializers import (
#     ShopSerializer,
#     ServiceSerializer,
#     OrderSerializer,
#     RegisterSerializer
# )




# # -------------------------------
# # REGISTER
# # -------------------------------
# class RegisterView(APIView):
#     permission_classes = [AllowAny]
#     authentication_classes = []

#     def post(self, request):
#         serializer = RegisterSerializer(data=request.data)

#         if serializer.is_valid():
#             serializer.save()
#             return Response({"message": "User created"}, status=201)

#         return Response(serializer.errors, status=400)


# # -------------------------------
# # LOGIN
# # -------------------------------
# class LoginView(APIView):
#     permission_classes = [AllowAny]
#     authentication_classes = []

#     def post(self, request):
#         username = request.data.get("username")
#         password = request.data.get("password")

#         user = authenticate(username=username, password=password)

#         if user is None:
#             return Response({"error": "Invalid credentials"}, status=401)

#         refresh = RefreshToken.for_user(user)

#         return Response({
#             "access": str(refresh.access_token),
#             "refresh": str(refresh),
#             "role": getattr(user, "role", "customer")
#         })


# # -------------------------------
# # SHOPS (🔥 SUBSCRIPTION REQUIRED)
# # -------------------------------
# class ShopListCreateView(generics.ListCreateAPIView):
#     serializer_class = ShopSerializer
#     permission_classes = [IsAuthenticated]

#     def get_queryset(self):
#         user = self.request.user

#         if user.role == "owner":
#             return Shop.objects.filter(owner=user)

#         return Shop.objects.all()

#     def create(self, request, *args, **kwargs):
#         user = request.user

        

#         return super().create(request, *args, **kwargs)

#     def perform_create(self, serializer):
#         serializer.save(owner=self.request.user)


# # -------------------------------
# # 🏠 FEATURED SHOPS
# # -------------------------------
# @api_view(['GET'])
# def featured_shops(request):
#     shops = list(Shop.objects.select_related('owner').all())
#     random.shuffle(shops)

#     unique_shops = []
#     owners_seen = set()

#     for shop in shops:
#         if shop.owner.id not in owners_seen:
#             unique_shops.append(shop)
#             owners_seen.add(shop.owner.id)

#         if len(unique_shops) == 4:
#             break

#     serializer = ShopSerializer(unique_shops, many=True)
#     return Response(serializer.data)


# # -------------------------------
# # SERVICES
# # -------------------------------
# class ServiceListCreateView(generics.ListCreateAPIView):
#     serializer_class = ServiceSerializer

#     def get_queryset(self):
#         queryset = Service.objects.all()
#         shop_id = self.request.query_params.get("shop")

#         if shop_id:
#             queryset = queryset.filter(shop_id=shop_id)

#         return queryset

#     def get_permissions(self):
#         if self.request.method == "POST":
#             return [IsAuthenticated()]
#         return [AllowAny()]

#     def perform_create(self, serializer):
#         shop_id = self.request.data.get("shop")

#         try:
#             shop = Shop.objects.get(id=shop_id, owner=self.request.user)
#         except Shop.DoesNotExist:
#             raise permissions.PermissionDenied("You do not own this shop")

#         serializer.save(shop=shop)


# # -------------------------------
# # CUSTOMER ORDERS
# # -------------------------------
# from rest_framework import generics
# from rest_framework.permissions import IsAuthenticated
# from .models import Order
# from .serializers import OrderSerializer


# class OrderListCreateView(generics.ListCreateAPIView):
#     serializer_class = OrderSerializer
#     permission_classes = [IsAuthenticated]

#     def get_queryset(self):
#         #  Customer sees only their orders
#         return Order.objects.filter(user=self.request.user)

#     def perform_create(self, serializer):
#         #  Attach logged-in user automatically
#         serializer.save(user=self.request.user)

# # 


# # -------------------------------
# # OWNER ORDERS
# # -------------------------------
# class OwnerOrderListView(generics.ListAPIView):
#     serializer_class = OrderSerializer
#     permission_classes = [IsAuthenticated]

#     def get_queryset(self):
#         user = self.request.user

#         if user.role != "owner":
#             raise permissions.PermissionDenied("Only owners can view this")

#         return Order.objects.filter(shop__owner=user)


# # -------------------------------
# # UPDATE ORDER STATUS
# # -------------------------------
# class UpdateOrderStatusView(generics.UpdateAPIView):
#     serializer_class = OrderSerializer
#     permission_classes = [IsAuthenticated]
#     queryset = Order.objects.all()

#     def update(self, request, *args, **kwargs):
#         order = self.get_object()

#         if order.shop.owner != request.user:
#             return Response({"error": "Not allowed"}, status=403)

#         order.status = request.data.get("status")
#         order.save()

#         return Response({"message": "Updated"})


# ===============================
# 🔥 MPESA SUBSCRIPTION SECTION
# ===============================

# -------------------------------
# PAY SUBSCRIPTION
# -------------------------------
# class PaySubscriptionView(APIView):
#     permission_classes = [IsAuthenticated]

#     def post(self, request):
#         phone = request.data.get("phone")

#         amount = 300  # 🔥 Monthly fee

#         response = stk_push(phone, amount, request.user.id)

#         return Response(response)


# # -------------------------------
# # CHECK SUBSCRIPTION (AUTO CHECK)
# # -------------------------------
# class CheckSubscriptionView(APIView):
#     permission_classes = [IsAuthenticated]

#     def get(self, request):
#         user = request.user

#         is_active = False

#         if user.subscription_expiry and user.subscription_expiry > now():
#             is_active = True

#         return Response({
#             "active": is_active,
#             "expiry": user.subscription_expiry
#         })


# # -------------------------------
# # MPESA CALLBACK
# # -------------------------------
# class MpesaCallbackView(APIView):
#     permission_classes = []

#     def post(self, request):
#         data = request.data

#         try:
#             result = data["Body"]["stkCallback"]

#             if result["ResultCode"] == 0:
#                 metadata = result["CallbackMetadata"]["Item"]

#                 phone = None
#                 for item in metadata:
#                     if item["Name"] == "PhoneNumber":
#                         phone = item["Value"]

#                 from django.contrib.auth import get_user_model
#                 User = get_user_model()

#                 user = User.objects.filter(phone=phone).first()

#                 if user:
#                     # 🔥 Extend subscription
#                     if user.subscription_expiry and user.subscription_expiry > now():
#                         user.subscription_expiry += timedelta(days=30)
#                     else:
#                         user.subscription_expiry = now() + timedelta(days=30)

#                     user.save()

#         except Exception as e:
#             print("Callback error:", e)

#         return Response({"message": "Callback received"})