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

    def __str__(self):
        return self.username


# =============================
# 🖼️ SAFE SHOP IMAGE UPLOAD
# =============================
def shop_image_upload(instance, filename):

    # split filename safely
    name, ext = os.path.splitext(filename)

    # slugify filename
    safe_name = slugify(name)

    # unique image name
    unique_name = (
        f"{safe_name}-{uuid.uuid4().hex[:8]}"
    )

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

    name = models.CharField(
        max_length=255
    )

    location = models.CharField(
        max_length=255
    )

    description = models.TextField()

    # ✅ IMAGE FIELD
    image = models.ImageField(
        upload_to=shop_image_upload,
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

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

    name = models.CharField(
        max_length=100
    )

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
        ("washing", "Washing"),
        ("completed", "Completed"),
    )

    PAYMENT_CHOICES = (
        ("pending", "Pending"),
        ("paid", "Paid"),
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

    # 💰 Total
    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )

    # 📞 Customer snapshot
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

    # 💳 Payment
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_CHOICES,
        default="pending",
    )

    # 🚦 Order status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    # 📁 ARCHIVE
    archived = models.BooleanField(
        default=False
    )

    archived_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):

        # calculate total price
        if self.service and self.weight:
            self.total_price = (
                Decimal(self.service.price_per_kg)
                * Decimal(self.weight)
            )

        # snapshot customer details
        if self.user:

            self.customer_phone = (
                self.user.phone
            )

            self.customer_location = (
                self.user.location
            )

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

#     def __str__(self):
#         return self.username


# # =============================
# # 🖼️ SAFE SHOP IMAGE UPLOAD
# # =============================
# def shop_image_upload(instance, filename):

#     # split filename safely
#     name, ext = os.path.splitext(filename)

#     # slugify filename
#     safe_name = slugify(name)

#     # unique image name
#     unique_name = (
#         f"{safe_name}-{uuid.uuid4().hex[:8]}"
#     )

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

#     name = models.CharField(
#         max_length=255
#     )

#     location = models.CharField(
#         max_length=255
#     )

#     description = models.TextField()

#     # ✅ IMAGE FIELD
#     image = models.ImageField(
#         upload_to=shop_image_upload,
#         blank=True,
#         null=True,
#     )

#     created_at = models.DateTimeField(
#         auto_now_add=True
#     )

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

#     name = models.CharField(
#         max_length=100
#     )

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

#     PAYMENT_CHOICES = (
#         ("pending", "Pending"),
#         ("paid", "Paid"),
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

#     # 💰 Total
#     total_price = models.DecimalField(
#         max_digits=10,
#         decimal_places=2,
#         blank=True,
#         null=True,
#     )

#     # 📞 Customer snapshot
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

#     # 💳 Payment
#     payment_status = models.CharField(
#         max_length=20,
#         choices=PAYMENT_CHOICES,
#         default="pending",
#     )

#     # 🚦 Order status
#     status = models.CharField(
#         max_length=20,
#         choices=STATUS_CHOICES,
#         default="pending",
#     )

#     created_at = models.DateTimeField(
#         auto_now_add=True
#     )

#     class Meta:
#         ordering = ["-created_at"]

#     def save(self, *args, **kwargs):

#         # calculate total price
#         if self.service and self.weight:
#             self.total_price = (
#                 Decimal(self.service.price_per_kg)
#                 * Decimal(self.weight)
#             )

#         # snapshot customer details
#         if self.user:

#             self.customer_phone = (
#                 self.user.phone
#             )

#             self.customer_location = (
#                 self.user.location
#             )

#         super().save(*args, **kwargs)

#     def __str__(self):

#         return (
#             f"{self.user.username} - "
#             f"{self.service.name} "
#             f"({self.status})"
#         )

        