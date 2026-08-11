import os
import uuid
from decimal import Decimal

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

    # ✅ Override username — remove global uniqueness.
    # Email is now the unique login identifier, so two people
    # named "steve" can exist as different roles.
    username = models.CharField(
        max_length=150,
        blank=False,
    )

    # ✅ Email is now unique — it's the login field
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
        blank=True,
        null=True,
    )

    # 📍 Location
    location = models.CharField(
        max_length=255,
        blank=True,
        null=True,
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