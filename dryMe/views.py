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
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Sum
import random

from .models import Order, Shop, Service
from .serializers import (
    ShopSerializer,
    ServiceSerializer,
    OrderSerializer,
    RegisterSerializer,
    ProfileSerializer,
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
        import traceback
        try:
            return self._post(request)
        except Exception as e:
            print("[LOGIN 500]", str(e))
            print("[LOGIN TRACEBACK]", traceback.format_exc())
            raise

    def _post(self, request):

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
            "id": user.id,
            "email": user.email,
            "role": getattr(
                user,
                "role",
                "customer"
            ),
            "username": user.username
        })


# ===============================
# 📊 PROFILE STATS HELPER
# ===============================
def build_profile_stats(user):

    if user.role == "owner":

        orders = Order.objects.filter(shop__owner=user)

        revenue = orders.filter(
            status="completed"
        ).aggregate(total=Sum("total_price"))["total"] or 0

        return {
            "shops_count": Shop.objects.filter(owner=user).count(),
            "total_orders": orders.count(),
            "active_orders": orders.filter(
                status__in=["pending", "confirmed", "washing"]
            ).count(),
            "completed_orders": orders.filter(status="completed").count(),
            "declined_orders": orders.filter(status="declined").count(),
            "revenue": revenue,
        }

    orders = Order.objects.filter(user=user)

    total_spent = orders.filter(
        payment_status="paid"
    ).aggregate(total=Sum("total_price"))["total"] or 0

    return {
        "total_orders": orders.count(),
        "active_orders": orders.filter(
            status__in=["pending", "confirmed", "washing"]
        ).count(),
        "completed_orders": orders.filter(status="completed").count(),
        "cancelled_orders": orders.filter(
            status__in=["cancelled", "declined"]
        ).count(),
        "total_spent": total_spent,
    }


# ===============================
# 👤 PROFILE (VIEW + UPDATE)
# ===============================
class ProfileView(generics.RetrieveUpdateAPIView):

    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    def retrieve(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object())
        data = dict(serializer.data)
        data["stats"] = build_profile_stats(request.user)
        return Response(data)


# ===============================
# 🔑 CHANGE PASSWORD
# ===============================
class ChangePasswordView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        user = request.user

        old_password = request.data.get("old_password", "")
        new_password = request.data.get("new_password", "")

        if not old_password or not new_password:
            return Response(
                {"error": "Both current and new password are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not user.check_password(old_password):
            return Response(
                {"error": "Current password is incorrect"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as e:
            return Response(
                {"error": " ".join(e.messages)},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(new_password)
        user.save()

        return Response({"message": "Password updated successfully"})


# ===============================
# 🏪 SHOPS (LIST + CREATE)
# ===============================
class ShopListCreateView(
    generics.ListCreateAPIView
):

    serializer_class = ShopSerializer
    parser_classes = (
        parsers.MultiPartParser,
        parsers.FormParser,
    )

    def get_permissions(self):
        # ✅ GET is public — anyone can browse shops
        # POST requires authentication (owners only)
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    # =========================
    # GET SHOPS
    # =========================
    def get_queryset(self):

        user = self.request.user

        # OWNERS SEE ONLY THEIR OWN SHOPS
        if user.is_authenticated and getattr(user, "role", "customer") == "owner":
            return Shop.objects.filter(
                owner=user
            ).order_by("-id")

        # GUESTS AND CUSTOMERS SEE ALL SHOPS
        return Shop.objects.all().order_by("-id")

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
    queryset = Shop.objects.all()

    def get_permissions(self):
        # ✅ GET is public — anyone can view a shop detail
        # PUT/PATCH/DELETE requires authentication
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

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
# 💳 MPESA STK PUSH
# ===============================
class MpesaSTKPushView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        from .mpesa import stk_push

        try:
            order = Order.objects.get(
                id=order_id,
                user=request.user
            )
        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        if order.payment_status == "paid":
            return Response(
                {"error": "Order is already paid"},
                status=status.HTTP_400_BAD_REQUEST
            )

        phone = request.user.phone
        if not phone:
            return Response(
                {"error": "No phone number on your account. Please update your profile."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not order.total_price:
            return Response(
                {"error": "Order total not calculated yet"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            response = stk_push(
                phone=phone,
                amount=order.total_price,
                order_id=order.id
            )
        except Exception as e:
            return Response(
                {"error": f"M-Pesa request failed: {str(e)}"},
                status=status.HTTP_502_BAD_GATEWAY
            )

        response_code = response.get("ResponseCode")

        if response_code == "0":
            # ✅ STK push sent — reset status and store checkout ID
            order.payment_status = "pending_payment"
            order.mpesa_checkout_request_id = response.get("CheckoutRequestID")
            order.mpesa_transaction_code = None
            order.save()

            return Response({
                "message": "Payment prompt sent to your phone. Enter your M-Pesa PIN to complete.",
                "checkout_request_id": response.get("CheckoutRequestID"),
            })

        else:
            order.payment_status = "failed"
            order.save()

            return Response(
                {"error": response.get("ResponseDescription", "STK push failed")},
                status=status.HTTP_400_BAD_REQUEST
            )


# ===============================
# 📩 MPESA CALLBACK
# ===============================
@api_view(["POST"])
@permission_classes([AllowAny])
@csrf_exempt
def mpesa_callback(request):
    try:
        body = request.data
        callback = body["Body"]["stkCallback"]
        result_code = callback["ResultCode"]
        checkout_request_id = callback["CheckoutRequestID"]

        try:
            order = Order.objects.get(
                mpesa_checkout_request_id=checkout_request_id
            )
        except Order.DoesNotExist:
            return Response({"status": "ok"})

        if result_code == 0:
            # ✅ Payment successful
            metadata = callback["CallbackMetadata"]["Item"]
            transaction_code = next(
                (item["Value"] for item in metadata if item["Name"] == "MpesaReceiptNumber"),
                None
            )
            order.payment_status = "paid"
            order.mpesa_transaction_code = transaction_code
            order.save()

        else:
            # ❌ Payment failed or cancelled
            order.payment_status = "failed"
            order.save()

    except Exception:
        pass

    # Always return 200 to Safaricom
    return Response({"status": "ok"})


# ===============================
# ✅ CHECK PAYMENT STATUS
# ===============================
class PaymentStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        try:
            order = Order.objects.get(
                id=order_id,
                user=request.user
            )
        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        return Response({
            "payment_status": order.payment_status,
            "mpesa_transaction_code": order.mpesa_transaction_code,
            "total_price": order.total_price,
        })


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

        queryset = Service.objects.all().order_by("id")

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
# 🧺 SERVICE DETAIL (EDIT + DELETE)
# ===============================
class ServiceDetailView(
    generics.RetrieveUpdateDestroyAPIView
):
    serializer_class = ServiceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Service.objects.all()

    def get_object(self):
        service = super().get_object()

        # Only the shop owner can edit or delete
        if self.request.method in ["PUT", "PATCH", "DELETE"]:
            if service.shop.owner != self.request.user:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied(
                    "You do not own this service."
                )
        return service

    def destroy(self, request, *args, **kwargs):
        service = self.get_object()

        # Warn instead of hard delete if orders exist
        has_orders = Order.objects.filter(
            service=service
        ).exists()

        if has_orders:
            return Response(
                {
                    "error": (
                        "Cannot delete this service because it has existing orders. "
                        "Consider renaming it instead."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        return super().destroy(request, *args, **kwargs)


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

        # 🚫 Declined/cancelled orders are a dead end — book again instead
        if order.status in ["declined", "cancelled"]:
            return Response(
                {"error": f"This order was {order.status} and can no longer be updated"},
                status=status.HTTP_400_BAD_REQUEST
            )

        new_status = request.data.get(
            "status"
        )

        valid_statuses = [
            "pending",
            "confirmed",
            "washing",
            "completed"
        ]

        if new_status not in valid_statuses:

            return Response(
                {"error": "Invalid status"},
                status=status.HTTP_400_BAD_REQUEST
            )

        from django.utils import timezone

        order.status = new_status

        # ⏱️ Auto-set timestamps when status changes
        if new_status == "confirmed" and not order.confirmed_at:
            order.confirmed_at = timezone.now()
        elif new_status == "washing" and not order.washing_at:
            order.washing_at = timezone.now()
        elif new_status == "completed" and not order.completed_at:
            order.completed_at = timezone.now()

        order.save()

        return Response({
            "message": "Order status updated"
        })


# ===============================
# ❌ DECLINE ORDER
# ===============================
class DeclineOrderView(APIView):

    permission_classes = [
        IsAuthenticated
    ]

    def post(self, request, pk):

        try:
            order = Order.objects.get(pk=pk)
        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # ONLY SHOP OWNER
        if order.shop.owner != request.user:
            return Response(
                {"error": "Not allowed"},
                status=status.HTTP_403_FORBIDDEN
            )

        # 🚫 Can only decline before washing starts — once washing/completed/
        # declined/cancelled, it's too late to turn the order away
        if order.status in ["washing", "completed", "declined", "cancelled"]:
            return Response(
                {"error": "This order can no longer be declined"},
                status=status.HTTP_400_BAD_REQUEST
            )

        reason = request.data.get("reason", "")
        reason = reason.strip() if isinstance(reason, str) else ""

        if not reason:
            return Response(
                {"error": "A reason is required to decline an order"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(reason) > 500:
            return Response(
                {"error": "Reason must be under 500 characters"},
                status=status.HTTP_400_BAD_REQUEST
            )

        from django.utils import timezone

        order.status = "declined"
        order.decline_reason = reason
        order.declined_at = timezone.now()

        # 💸 Flag for manual refund if the customer already paid
        if order.payment_status == "paid":
            order.refund_needed = True

        order.save()

        return Response({
            "message": "Order declined",
            "status": order.status,
            "decline_reason": order.decline_reason,
            "refund_needed": order.refund_needed,
        })


# ===============================
# 🚫 CANCEL ORDER (customer)
# ===============================
class CancelOrderView(APIView):

    permission_classes = [
        IsAuthenticated
    ]

    def post(self, request, pk):

        try:
            order = Order.objects.get(pk=pk)
        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # ONLY THE CUSTOMER WHO PLACED IT
        if order.user != request.user:
            return Response(
                {"error": "Not allowed"},
                status=status.HTTP_403_FORBIDDEN
            )

        # 🚫 Can only cancel before washing starts
        if order.status in ["washing", "completed", "declined", "cancelled"]:
            return Response(
                {"error": "This order can no longer be cancelled"},
                status=status.HTTP_400_BAD_REQUEST
            )

        from django.utils import timezone

        order.status = "cancelled"
        order.cancelled_at = timezone.now()

        # 💸 Flag for manual refund if the customer already paid
        if order.payment_status == "paid":
            order.refund_needed = True

        order.save()

        return Response({
            "message": "Order cancelled",
            "status": order.status,
            "refund_needed": order.refund_needed,
        })


# ===============================
# 📝 UPDATE ORDER NOTES
# ===============================
class UpdateOrderNotesView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, pk):
        try:
            order = Order.objects.get(
                id=pk,
                user=request.user
            )
        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        notes = request.data.get("notes", "")
        order.customer_notes = notes
        order.save()

        return Response({
            "message": "Notes updated",
            "notes": order.customer_notes,
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

        # ONLY TERMINAL ORDERS — nothing left to happen to them
        if order.status not in ["completed", "declined", "cancelled"]:

            return Response(
                {
                    "error":
                    "Only completed, declined, or cancelled orders can be archived"
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