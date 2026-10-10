import os
import uuid
from decimal import Decimal, ROUND_HALF_UP

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.text import slugify


# =============================
# 👤 CUSTOM USER
# =============================
class User(AbstractUser):

    ROLE_CHOICES = (
        ("customer", "Customer"),
        ("owner", "Owner"),
    )

    
    username = models.CharField(
        max_length=150,
        blank=False,
    )

    #Email is now unique — it's the login field
    email = models.EmailField(
        unique=True,
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="customer",
    )

    # 📞 Phone
    phone = models.CharField(
        max_length=15,
        blank=False,
        null=False,
    )

    # 📍 Location
    location = models.CharField(
        max_length=255,
        blank=False,
        null=False,
    )

    # Tell Django to use email as the unique identifier for auth
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        return f"{self.username} ({self.email})"


# =============================
# 🖼️ SAFE SHOP IMAGE UPLOAD
# =============================
def shop_image_upload(instance, filename):

    name, ext = os.path.splitext(filename)
    safe_name = slugify(name)
    unique_name = f"{safe_name}-{uuid.uuid4().hex[:8]}"

    return f"shops/{unique_name}{ext}"


# =============================
# 🏪 SHOP MODEL
# =============================
class Shop(models.Model):

    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="shops",
    )

    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    description = models.TextField()

    # 📍 Exact GPS pin for the shop itself — lets customers see and
    # navigate to the real spot instead of just a typed neighborhood
    # name. FloatField (not DecimalField) deliberately, to avoid the
    # same over-precision rejection bug we hit with Order.pickup_lat/lng.
    lat = models.FloatField(blank=True, null=True)
    lng = models.FloatField(blank=True, null=True)

    image = models.ImageField(
        upload_to=shop_image_upload,
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


# =============================
# 🧺 SERVICE MODEL
# =============================
class Service(models.Model):

    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        related_name="services",
    )

    name = models.CharField(max_length=100)

    # 💲 How this service is priced. "per_kg" — regular wash/dry-clean
    # by weight. "per_item" — suits, duvets, curtains, anything priced
    # per piece rather than by weight.
    PRICING_TYPE_CHOICES = (
        ("per_kg", "Per Kg"),
        ("per_item", "Per Item"),
    )

    pricing_type = models.CharField(
        max_length=10,
        choices=PRICING_TYPE_CHOICES,
        default="per_kg",
    )

    # Price per kg (if pricing_type="per_kg") or price per item
    # (if pricing_type="per_item") — same field, meaning depends on type.
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    def __str__(self):
        return f"{self.name} - {self.shop.name}"


# =============================
# 📦 ORDER MODEL
# =============================
class Order(models.Model):

    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("washing", "Washing"),
        ("completed", "Completed"),
        ("declined", "Declined"),
        ("cancelled", "Cancelled"),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="orders",
    )

    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        related_name="orders",
    )

    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
    )

    weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
    )

    # Used instead of weight when the service is priced per item
    # (e.g. "3 suits").
    quantity = models.PositiveIntegerField(
        blank=True,
        null=True,
    )

    # 💰 Auto-calculated total
    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )

    # 📝 Customer notes (gate code, stain alerts, instructions)
    customer_notes = models.TextField(
        blank=True,
        null=True,
    )

    # 📞 Customer snapshot at time of order
    customer_phone = models.CharField(
        max_length=15,
        blank=True,
        null=True,
    )

    customer_location = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    # 📍 Optional GPS pin — captured from the browser's geolocation at
    # booking time. When present, this is what drivers/owners should use
    # for directions (an exact point), with customer_location kept as a
    # human-readable landmark/detail ("blue gate opposite Java House").
    pickup_lat = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        blank=True,
        null=True,
    )

    pickup_lng = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        blank=True,
        null=True,
    )

    # 💳 Payment status
    PAYMENT_STATUS_CHOICES = (
        ("unpaid", "Unpaid"),
        ("pending_payment", "Pending Payment"),
        ("paid", "Paid"),
        ("failed", "Failed"),
    )

    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default="unpaid",
    )

    # M-Pesa checkout request ID for tracking
    mpesa_checkout_request_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    # M-Pesa transaction code after successful payment
    mpesa_transaction_code = models.CharField(
        max_length=50,
        blank=True,
        null=True,
    )

    # 🚦 Order status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    # ❌ Why the owner declined the order (required when status="declined")
    decline_reason = models.TextField(
        blank=True,
        null=True,
    )

    # 💸 Flags a declined order that was already paid, so the owner
    # knows to issue a manual M-Pesa refund
    refund_needed = models.BooleanField(default=False)
        # 💰 Settlement snapshot (filled by services.wallet.settle_order)
    # amount_paid = what M-Pesa actually delivered (whole shillings).
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    owner_earnings = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    settled_at = models.DateTimeField(blank=True, null=True)

    # 📁 Archive flags (independent per role)
    customer_archived = models.BooleanField(default=False)
    owner_archived = models.BooleanField(default=False)

    # ⏱️ Timeline timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    confirmed_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    washing_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    completed_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    declined_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    cancelled_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):

        # ✅ Always recalculate total price — how depends on how this
        # service is priced.
        if self.service:
            if self.service.pricing_type == "per_item" and self.quantity:
                self.total_price = (
                    Decimal(self.service.price)
                    * Decimal(self.quantity)
                )
            elif self.service.pricing_type == "per_kg" and self.weight:
                self.total_price = (
                    Decimal(self.service.price)
                    * Decimal(self.weight)
                )

        # ✅ Snapshot customer details on creation — only fills in from
        # the profile as a fallback; an explicitly provided per-order
        # phone/location (from the booking form) always wins.
        is_new = self.pk is None
        if is_new and self.user:
            if not self.customer_phone:
                self.customer_phone = self.user.phone
            if not self.customer_location:
                self.customer_location = self.user.location

        super().save(*args, **kwargs)

    def payable_amount(self):
        """Whole-shilling amount sent in the STK push (Daraja takes integers)."""
        return int((self.total_price or Decimal("0")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def __str__(self):
        return (
            f"{self.user.username} - "
            f"{self.service.name} "
            f"({self.status})"
        )


# =============================
# ⭐ REVIEW MODEL
# =============================
class Review(models.Model):

    # One review per completed order — this is what ties eligibility
    # ("did you actually get laundry back from this shop") to the
    # ability to review at all, and stops one order being reviewed twice.
    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name="review",
    )

    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        related_name="reviews",
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="reviews",
    )

    rating = models.PositiveSmallIntegerField(
        choices=[(i, str(i)) for i in range(1, 6)],
    )

    comment = models.TextField(
        max_length=1000,
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} rated {self.shop.name} {self.rating}★"


# =============================
# 🔔 NOTIFICATION MODEL
# =============================
class Notification(models.Model):

    # Who this notification is for — a customer (order status update)
    # or an owner (new order / new review).
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications",
    )

    NOTIF_TYPE_CHOICES = (
        ("order_confirmed", "Order Confirmed"),
        ("order_washing", "Order Washing"),
        ("order_completed", "Order Completed"),
        ("order_declined", "Order Declined"),
        ("order_cancelled", "Order Cancelled"),
        ("new_review", "New Review"),
    )

    notif_type = models.CharField(
        max_length=20,
        choices=NOTIF_TYPE_CHOICES,
    )

    message = models.CharField(max_length=255)

    # Optional links back to the thing this notification is about, so
    # the frontend can navigate there on click. Both optional since a
    # notification might relate to an order, a review, or neither.
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="notifications",
    )

    review = models.ForeignKey(
        Review,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="notifications",
    )

    is_read = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"→ {self.user.username}: {self.message}"


# =============================
# 👛 WALLET
# =============================
class Wallet(models.Model):

    # PROTECT: a user holding money can't be hard-deleted by accident.
    owner = models.OneToOneField(User, on_delete=models.PROTECT, related_name="wallet")
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(balance__gte=0), name="wallet_balance_non_negative"),
        ]

    def __str__(self):
        return f"{self.owner.username}: KES {self.balance}"


# =============================
# 💸 PAYOUT (withdrawal request)
# =============================
class Payout(models.Model):

    METHOD_CHOICES = (("mpesa", "M-Pesa"), ("bank", "Bank"))
    STATUS_CHOICES = (
        ("requested", "Requested"),
        ("approved", "Approved"),
        ("paid", "Paid"),
        ("rejected", "Rejected"),
        ("failed", "Failed"),
    )

    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name="payouts")

    # amount = gross, leaves the wallet. fee = snapshotted at request time.
    # net_amount = amount - fee = what you actually send.
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    fee = models.DecimalField(max_digits=10, decimal_places=2)
    net_amount = models.DecimalField(max_digits=10, decimal_places=2)

    method = models.CharField(max_length=10, choices=METHOD_CHOICES)
    destination = models.CharField(max_length=255)  # 2547… for M-Pesa, free text for bank
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="requested")

    reference = models.CharField(max_length=100, blank=True, default="")  # M-Pesa code / bank ref
    reject_reason = models.TextField(blank=True, default="")

    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_payouts",
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)
    paid_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-requested_at"]
        constraints = [
            # One open payout per owner — enforced by the database, not just the service.
            models.UniqueConstraint(
                fields=["owner"],
                condition=models.Q(status__in=["requested", "approved"]),
                name="one_open_payout_per_owner",
            ),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="payout_amount_positive"),
            models.CheckConstraint(condition=models.Q(net_amount__gt=0), name="payout_net_positive"),
            models.CheckConstraint(
                condition=models.Q(net_amount=models.F("amount") - models.F("fee")),
                name="payout_net_equals_amount_minus_fee",
            ),
        ]

    def __str__(self):
        return f"Payout #{self.pk} {self.owner.username} KES {self.amount} ({self.status})"


# =============================
# 📒 WALLET LEDGER (append-only)
# =============================
class WalletTransaction(models.Model):

    TYPE_CHOICES = (
        ("sale_credit", "Sale credit"),
        ("payout_hold", "Payout hold"),
        ("payout_reversal", "Payout reversal"),
        ("adjustment", "Adjustment"),
    )

    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name="transactions")
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)          # signed
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)

    # SET_NULL: deleting a shop cascades to its orders — the money trail must survive.
    order = models.ForeignKey(
        Order, on_delete=models.SET_NULL, null=True, blank=True, related_name="wallet_transactions",
    )
    payout = models.ForeignKey(
        Payout, on_delete=models.PROTECT, null=True, blank=True, related_name="wallet_transactions",
    )
    note = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["order"],
                condition=models.Q(type="sale_credit"),
                name="uniq_sale_credit_per_order",
            ),
            models.UniqueConstraint(
                fields=["payout", "type"],
                condition=models.Q(payout__isnull=False),
                name="uniq_ledger_entry_per_payout_type",
            ),
        ]

    def __str__(self):
        return f"{self.type} {self.amount} → {self.balance_after}"