from django.utils import timezone
from decimal import Decimal
from datetime import timedelta
from rest_framework import generics, permissions, parsers, status
from rest_framework.permissions import (
    IsAuthenticated,
    AllowAny
)
from rest_framework.decorators import (
    api_view,
    permission_classes
)

from rest_framework.exceptions import ValidationError as ApiValidationError
from rest_framework.exceptions import PermissionDenied as DrfPermissionDenied
from .services.notifications import notify


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

import hmac
import logging

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.decorators import authentication_classes
from .services.payments import process_stk_callback

from .services.wallet import settle_order
logger = logging.getLogger(__name__)



from .models import Order, Shop, Service, Review, Notification, PaymentAttempt
from .serializers import (
    ShopSerializer,
    ServiceSerializer,
    OrderSerializer,
    RegisterSerializer,
    ProfileSerializer,
    ReviewSerializer,
    NotificationSerializer,
    
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

# ====================================================================
# 📊 PROFILE STATS HELPER (Standardized Formatting & Precise Auditing)
# ====================================================================
def build_profile_stats(user):

    if user.role == "owner":
        orders = Order.objects.filter(shop__owner=user)

        # Gross sales = money actually received (amount_paid from M-Pesa) on orders completed.
        # Unpaid, declined, and cancelled orders are skipped. Enforces strict ledger alignment:
        # earnings = gross sales - commission. Sent as an exact 2-decimal text string.
        gross_sales = orders.filter(
            status="completed",
            payment_status="paid",
        ).aggregate(total=Sum("amount_paid"))["total"] or Decimal("0.00")

        return {
            "shops_count": Shop.objects.filter(owner=user).count(),
            "total_orders": orders.count(),
            "active_orders": orders.filter(
                status__in=["pending", "confirmed", "washing"]
            ).count(),
            "completed_orders": orders.filter(status="completed").count(),
            "declined_orders": orders.filter(status="declined").count(),
            # ✅ Forces exact 2-decimal tracking strings to clear the '400' vs '400.00' mismatch
            "revenue": f"{gross_sales:.2f}",
        }

    # ==========================================
    # 👤 CUSTOMER BRANCH
    # ==========================================
    orders = Order.objects.filter(user=user)

    # Total spent = what the customer actually paid (amount_paid from M-Pesa) on orders that
    # weren't declined or cancelled. Those get refunded, so they aren't spending.
    # Paid orders still in progress DO count: the money has left and the service is on its way.
    total_spent = orders.filter(
        payment_status="paid",
    ).exclude(
        status__in=["declined", "cancelled"],
    ).aggregate(total=Sum("amount_paid"))["total"] or Decimal("0.00") # ✅ Changed to amount_paid

    return {
        "total_orders": orders.count(),
        "active_orders": orders.filter(
            status__in=["pending", "confirmed", "washing"]
        ).count(),
        "completed_orders": orders.filter(status="completed").count(),
        "cancelled_orders": orders.filter(
            status__in=["cancelled", "declined"]
        ).count(),
        # ✅ Standardized as a 2-decimal text string token to resolve test client validation
        "total_spent": f"{total_spent:.2f}",
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
            order = Order.objects.get(id=order_id, user=request.user)
        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if order.status in ("declined", "cancelled"):
            return Response(
                {"error": "This order is no longer active"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if order.payment_status == "paid":
            return Response(
                {"error": "Order is already paid"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        phone = request.user.phone
        if not phone:
            return Response(
                {"error": "No phone number on your account. Please update your profile."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        amount = order.payable_amount()
        if amount < 1:
            return Response(
                {"error": "Order total not calculated yet"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Best-effort guard against double taps. Each prompt has its own attempt.
        cooldown = getattr(settings, "MPESA_STK_COOLDOWN_SECONDS", 60)
        if cooldown > 0:
            cutoff = timezone.now() - timedelta(seconds=cooldown)
            if order.payment_attempts.filter(
                status=PaymentAttempt.Status.PENDING,
                created_at__gte=cutoff,
            ).exists():
                return Response(
                    {
                        "error": (
                            "A payment prompt was just sent to your phone. Enter your "
                            "M-Pesa PIN, or wait a minute before trying again."
                        )
                    },
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

        try:
            response = stk_push(phone=phone, amount=amount, order_id=order.id)
        except Exception:
            logger.exception("STK push failed for order=%s", order.id)
            return Response(
                {"error": "Couldn't reach M-Pesa. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if response.get("ResponseCode") == "0":
            checkout_id = response.get("CheckoutRequestID")
            if not checkout_id:
                logger.error(
                    "STK push accepted without CheckoutRequestID order=%s",
                    order.id,
                )
                return Response(
                    {"error": "M-Pesa returned an unexpected response. Please try again."},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            with transaction.atomic():
                PaymentAttempt.objects.create(
                    order=order,
                    checkout_request_id=checkout_id,
                    amount=Decimal(amount),
                )
                # Avoid downgrading an order already marked paid by a callback.
                Order.objects.filter(pk=order.pk).exclude(
                    payment_status="paid"
                ).update(payment_status="pending_payment")

            return Response(
                {
                    "message": (
                        "Payment prompt sent to your phone. Enter your M-Pesa PIN "
                        "to complete."
                    ),
                    "checkout_request_id": checkout_id,
                }
            )

        # No attempt row exists when Safaricom refuses to send the prompt.
        Order.objects.filter(
            pk=order.pk,
            payment_status="unpaid",
        ).update(payment_status="failed")

        return Response(
            {"error": response.get("ResponseDescription", "STK push failed")},
            status=status.HTTP_400_BAD_REQUEST,
        )


# ===============================
# 📩 MPESA CALLBACK
# ===============================
def _client_ip(request):
    # Use the rightmost forwarded hop, which should be added by our trusted proxy.
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[-1].strip()
    return request.META.get("REMOTE_ADDR")


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def mpesa_callback(request, secret):
    expected = getattr(settings, "MPESA_CALLBACK_SECRET", "")

    # Fail closed if the secret is not configured or the URL secret is incorrect.
    if not expected or not hmac.compare_digest(str(secret), str(expected)):
        return Response(status=status.HTTP_404_NOT_FOUND)

    allowed_ips = getattr(settings, "MPESA_CALLBACK_ALLOWED_IPS", [])
    client_ip = _client_ip(request)
    if allowed_ips and client_ip not in allowed_ips:
        logger.warning("M-Pesa callback from non-allowlisted IP %s", client_ip)
        return Response(status=status.HTTP_404_NOT_FOUND)

    try:
        outcome = process_stk_callback(request.data)
        logger.info("M-Pesa callback outcome=%s", outcome)
    except Exception:
        logger.exception("M-Pesa callback processing failed")

    # Acknowledge the callback so Safaricom does not repeatedly retry it.
    return Response({"ResultCode": 0, "ResultDesc": "Accepted"})


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

# ====================================================================
# 🧺 OWNER ORDERS (Hardened Pagination & Dynamic Status Filtering)
# ====================================================================
class OwnerOrderListView(generics.ListAPIView):
    """
    GET owner/orders/?status=pending&page=2
    Active (not archived) orders for this owner's shops, newest first, 10 per page.
    ?status= filters BEFORE pagination, so older orders are always reachable.
    """

    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, "role", "customer")

        if role != "owner":
            # ✅ Fixed the AttributeError exception mapping securely via DRF Exceptions layer
            raise DrfPermissionDenied("Only owners can view this")

        queryset = (
            Order.objects
            .filter(shop__owner=user, owner_archived=False)
            .select_related("user", "shop__owner", "service", "review")
            .order_by("-created_at", "-id")
        )

        status_filter = self.request.query_params.get("status")
        if status_filter:
            # Enforces evaluation constraints across active schema structures
            valid = {value for value, _label in Order.STATUS_CHOICES}
            if status_filter not in valid:
                raise ApiValidationError({"status": f"Unknown status '{status_filter}'."})
            queryset = queryset.filter(status=status_filter)

        return queryset




class UpdateOrderStatusView(
    generics.UpdateAPIView
):

    serializer_class = OrderSerializer
    permission_classes = [
        IsAuthenticated
    ]

    queryset = Order.objects.all()

    def update(self, request, *args, **kwargs):
        from django.utils import timezone

        notification = None

        with transaction.atomic():
            order = get_object_or_404(
                Order.objects.select_for_update(),
                pk=kwargs["pk"]
            )

            # ONLY SHOP OWNER
            if order.shop.owner != request.user:
                return Response(
                    {"error": "Not allowed"},
                    status=status.HTTP_403_FORBIDDEN
                )

            # Declined/cancelled orders cannot be updated.
            if order.status in ["declined", "cancelled"]:
                return Response(
                    {"error": f"This order was {order.status} and can no longer be updated"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Completed is final because earnings may already be credited.
            if order.status == "completed":
                return Response(
                    {"error": "This order is already completed"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            new_status = request.data.get("status")
            if new_status not in ["pending", "confirmed", "washing", "completed"]:
                return Response(
                    {"error": "Invalid status"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            order.status = new_status
            fields = ["status"]
            now = timezone.now()

            # Automatically set timestamps when the status first reaches a stage.
            if new_status == "confirmed" and not order.confirmed_at:
                order.confirmed_at = now
                fields.append("confirmed_at")
            elif new_status == "washing" and not order.washing_at:
                order.washing_at = now
                fields.append("washing_at")
            elif new_status == "completed" and not order.completed_at:
                order.completed_at = now
                fields.append("completed_at")

            order.save(update_fields=fields)

            # Credit the owner's wallet when an order is completed.
            if new_status == "completed":
                settle_order(order.pk)

            status_messages = {
                "confirmed": ("order_confirmed", f"{order.shop.name} confirmed your order"),
                "washing": ("order_washing", f"{order.shop.name} started washing your order"),
                "completed": ("order_completed", f"{order.shop.name} completed your order — ready for pickup"),
            }
            notification = status_messages.get(new_status)

        # Notify after the transaction so notification failures do not undo order updates.
        if notification:
            notify(order.user, notification[0], notification[1], order=order)

        return Response({"message": "Order status updated"})


# ===============================
# 🔔 MARK NOTIFICATIONS AS READ
# ===============================
class NotificationMarkReadView(APIView):

    permission_classes = [
        IsAuthenticated
    ]

    def put(self, request):

        Notification.objects.filter(
            user=request.user,
            is_read=False
        ).update(
            is_read=True
        )

        return Response({
            "message": "Notifications marked as read"
        })


# ===============================
# 🔔 UNREAD NOTIFICATION COUNT
# ===============================
class UnreadNotificationCountView(APIView):

    permission_classes = [
        IsAuthenticated
    ]

    def get(self, request):

        count = Notification.objects.filter(
            user=request.user,
            is_read=False
        ).count()

        return Response({
            "count": count
        })

# ===============================
# ❌ DECLINE ORDER
# ===============================
class DeclineOrderView(APIView):

    permission_classes = [
        IsAuthenticated
    ]

    def post(self, request, pk):
        from django.utils import timezone

        reason = request.data.get("reason", "")
        reason = reason.strip() if isinstance(reason, str) else ""

        with transaction.atomic():
            order = Order.objects.select_for_update().filter(pk=pk).first()
            if order is None:
                return Response(
                    {"error": "Order not found"},
                    status=status.HTTP_404_NOT_FOUND
                )

            if order.shop.owner != request.user:
                return Response(
                    {"error": "Not allowed"},
                    status=status.HTTP_403_FORBIDDEN
                )

            if order.status in ["washing", "completed", "declined", "cancelled"]:
                return Response(
                    {"error": "This order can no longer be declined"},
                    status=status.HTTP_400_BAD_REQUEST
                )

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

            order.status = "declined"
            order.decline_reason = reason
            order.declined_at = timezone.now()
            if order.payment_status == "paid":
                order.refund_needed = True

            order.save(update_fields=[
                "status",
                "decline_reason",
                "declined_at",
                "refund_needed",
            ])

        notify(
            order.user,
            "order_declined",
            f"{order.shop.name} declined your order",
            order=order
        )

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
        from django.utils import timezone

        with transaction.atomic():
            order = Order.objects.select_for_update().filter(pk=pk).first()
            if order is None:
                return Response(
                    {"error": "Order not found"},
                    status=status.HTTP_404_NOT_FOUND
                )

            if order.user != request.user:
                return Response(
                    {"error": "Not allowed"},
                    status=status.HTTP_403_FORBIDDEN
                )

            if order.status in ["washing", "completed", "declined", "cancelled"]:
                return Response(
                    {"error": "This order can no longer be cancelled"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            order.status = "cancelled"
            order.cancelled_at = timezone.now()
            if order.payment_status == "paid":
                order.refund_needed = True

            order.save(update_fields=[
                "status",
                "cancelled_at",
                "refund_needed",
            ])

        notify(
            order.shop.owner,
            "order_cancelled",
            f"{order.user.username} cancelled their order at {order.shop.name}",
            order=order,
        )

        return Response({
            "message": "Order cancelled",
            "status": order.status,
            "refund_needed": order.refund_needed,
        })


# ===============================
# ⭐ CREATE REVIEW (for a completed order)
# ===============================
class CreateReviewView(APIView):

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

        # 🚫 Can only review an order the shop actually completed
        if order.status != "completed":
            return Response(
                {"error": "You can only review an order after it's completed"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 🚫 One review per order
        if hasattr(order, "review"):
            return Response(
                {"error": "You've already reviewed this order"},
                status=status.HTTP_400_BAD_REQUEST
            )

        rating = request.data.get("rating")
        comment = request.data.get("comment", "")

        if rating is None:
            return Response(
                {"error": "A rating is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            rating = int(rating)
        except (TypeError, ValueError):
            return Response(
                {"error": "Rating must be a number from 1 to 5"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if rating < 1 or rating > 5:
            return Response(
                {"error": "Rating must be between 1 and 5"},
                status=status.HTTP_400_BAD_REQUEST
            )

        review = Review.objects.create(
            order=order,
            shop=order.shop,
            user=request.user,
            rating=rating,
            comment=comment.strip() if isinstance(comment, str) else "",
        )

        # 🔔 Notify the shop owner
        stars = "★" * rating
        notify(
            order.shop.owner,
            "new_review",
            f"{request.user.username} left a {stars} review for {order.shop.name}",
            review=review,
        )

        serializer = ReviewSerializer(review)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# ===============================
# ⭐ LIST REVIEWS FOR A SHOP (public)
# ===============================
class ShopReviewsView(generics.ListAPIView):

    serializer_class = ReviewSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        shop_id = self.kwargs["pk"]
        return Review.objects.filter(shop_id=shop_id).select_related("user")


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
        order.save( update_fields=["customer_notes"])

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
            order.save( update_fields=["customer_archived"])

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
            order.save( update_fields=["owner_archived"])

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


# ===============================
# 🔔 NOTIFICATIONS
# ===============================
class NotificationListView(generics.ListAPIView):

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        unread_count = self.get_queryset().filter(is_read=False).count()
        # Keep pagination (if enabled) intact by attaching unread_count
        # alongside whatever shape .data already has.
        if isinstance(response.data, dict):
            response.data["unread_count"] = unread_count
        else:
            response.data = {
                "results": response.data,
                "unread_count": unread_count,
            }
        return response


class MarkNotificationReadView(APIView):

    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        try:
            notification = Notification.objects.get(pk=pk, user=request.user)
        except Notification.DoesNotExist:
            return Response(
                {"error": "Notification not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        notification.is_read = True
        notification.save()

        return Response({"message": "Marked as read"})


class MarkAllNotificationsReadView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):
        Notification.objects.filter(
            user=request.user,
            is_read=False,
        ).update(is_read=True)

        return Response({"message": "All notifications marked as read"})
