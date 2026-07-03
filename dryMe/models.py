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

    price_per_kg = models.DecimalField(
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

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):

        # ✅ Always recalculate total price
        if self.service and self.weight:
            self.total_price = (
                Decimal(self.service.price_per_kg)
                * Decimal(self.weight)
            )

        # ✅ Only snapshot customer details on creation
        is_new = self.pk is None
        if is_new and self.user:
            self.customer_phone = self.user.phone
            self.customer_location = self.user.location

        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.user.username} - "
            f"{self.service.name} "
            f"({self.status})"
        )


# import os
# import uuid
# from decimal import Decimal

# from django.db import models
# from django.contrib.auth.models import AbstractUser
# from django.utils.text import slugify


# # =============================
# # 👤 CUSTOM USER
# # =============================
# class User(AbstractUser):

#     ROLE_CHOICES = (
#         ("customer", "Customer"),
#         ("owner", "Owner"),
#     )

#     # ✅ Override username — remove global uniqueness.
#     # Email is now the unique login identifier, so two people
#     # named "steve" can exist as different roles.
#     username = models.CharField(
#         max_length=150,
#         blank=False,
#     )

#     # ✅ Email is now unique — it's the login field
#     email = models.EmailField(
#         unique=True,
#     )

#     role = models.CharField(
#         max_length=20,
#         choices=ROLE_CHOICES,
#         default="customer",
#     )

#     # 📞 Phone
#     phone = models.CharField(
#         max_length=15,
#         blank=True,
#         null=True,
#     )

#     # 📍 Location
#     location = models.CharField(
#         max_length=255,
#         blank=True,
#         null=True,
#     )

#     # Tell Django to use email as the unique identifier for auth
#     USERNAME_FIELD = "email"
#     REQUIRED_FIELDS = ["username"]

#     def __str__(self):
#         return f"{self.username} ({self.email})"


# # =============================
# # 🖼️ SAFE SHOP IMAGE UPLOAD
# # =============================
# def shop_image_upload(instance, filename):

#     name, ext = os.path.splitext(filename)
#     safe_name = slugify(name)
#     unique_name = f"{safe_name}-{uuid.uuid4().hex[:8]}"

#     return f"shops/{unique_name}{ext}"


# # =============================
# # 🏪 SHOP MODEL
# # =============================
# class Shop(models.Model):

#     owner = models.ForeignKey(
#         User,
#         on_delete=models.CASCADE,
#         related_name="shops",
#     )

#     name = models.CharField(max_length=255)
#     location = models.CharField(max_length=255)
#     description = models.TextField()

#     image = models.ImageField(
#         upload_to=shop_image_upload,
#         blank=True,
#         null=True,
#     )

#     created_at = models.DateTimeField(auto_now_add=True)

#     class Meta:
#         ordering = ["-created_at"]

#     def __str__(self):
#         return self.name


# # =============================
# # 🧺 SERVICE MODEL
# # =============================
# class Service(models.Model):

#     shop = models.ForeignKey(
#         Shop,
#         on_delete=models.CASCADE,
#         related_name="services",
#     )

#     name = models.CharField(max_length=100)

#     price_per_kg = models.DecimalField(
#         max_digits=10,
#         decimal_places=2,
#     )

#     def __str__(self):
#         return f"{self.name} - {self.shop.name}"


# # =============================
# # 📦 ORDER MODEL
# # =============================
# class Order(models.Model):

#     STATUS_CHOICES = (
#         ("pending", "Pending"),
#         ("washing", "Washing"),
#         ("completed", "Completed"),
#     )

#     user = models.ForeignKey(
#         User,
#         on_delete=models.CASCADE,
#         related_name="orders",
#     )

#     shop = models.ForeignKey(
#         Shop,
#         on_delete=models.CASCADE,
#         related_name="orders",
#     )

#     service = models.ForeignKey(
#         Service,
#         on_delete=models.CASCADE,
#     )

#     weight = models.DecimalField(
#         max_digits=5,
#         decimal_places=2,
#     )

#     # 💰 Auto-calculated total
#     total_price = models.DecimalField(
#         max_digits=10,
#         decimal_places=2,
#         blank=True,
#         null=True,
#     )

#     # 📞 Customer snapshot at time of order
#     customer_phone = models.CharField(
#         max_length=15,
#         blank=True,
#         null=True,
#     )

#     customer_location = models.CharField(
#         max_length=255,
#         blank=True,
#         null=True,
#     )

#     # 💳 Payment status
#     PAYMENT_STATUS_CHOICES = (
#         ("unpaid", "Unpaid"),
#         ("pending_payment", "Pending Payment"),
#         ("paid", "Paid"),
#         ("failed", "Failed"),
#     )

#     payment_status = models.CharField(
#         max_length=20,
#         choices=PAYMENT_STATUS_CHOICES,
#         default="unpaid",
#     )

#     # M-Pesa checkout request ID for tracking
#     mpesa_checkout_request_id = models.CharField(
#         max_length=100,
#         blank=True,
#         null=True,
#     )

#     # M-Pesa transaction code after successful payment
#     mpesa_transaction_code = models.CharField(
#         max_length=50,
#         blank=True,
#         null=True,
#     )

#     # 🚦 Order status
#     status = models.CharField(
#         max_length=20,
#         choices=STATUS_CHOICES,
#         default="pending",
#     )

#     # 📁 Archive flags (independent per role)
#     customer_archived = models.BooleanField(default=False)
#     owner_archived = models.BooleanField(default=False)

#     # ⏱️ Timeline timestamps
#     created_at = models.DateTimeField(auto_now_add=True)

#     washing_at = models.DateTimeField(
#         blank=True,
#         null=True,
#     )

#     completed_at = models.DateTimeField(
#         blank=True,
#         null=True,
#     )

#     class Meta:
#         ordering = ["-created_at"]

#     def save(self, *args, **kwargs):

#         # ✅ Always recalculate total price
#         if self.service and self.weight:
#             self.total_price = (
#                 Decimal(self.service.price_per_kg)
#                 * Decimal(self.weight)
#             )

#         # ✅ Only snapshot customer details on creation
#         is_new = self.pk is None
#         if is_new and self.user:
#             self.customer_phone = self.user.phone
#             self.customer_location = self.user.location

#         super().save(*args, **kwargs)

#     def __str__(self):
#         return (
#             f"{self.user.username} - "
#             f"{self.service.name} "
#             f"({self.status})"
#         )

