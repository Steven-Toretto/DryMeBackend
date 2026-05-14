import os
import uuid
from decimal import Decimal

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.text import slugify


# =============================
#  Custom User
# =============================
class User(AbstractUser):
    ROLE_CHOICES = (
        ('customer', 'Customer'),
        ('owner', 'Owner'),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='customer')

    # Phone 
    phone = models.CharField(max_length=15, null=True, blank=True)

    # Location
    location = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return self.username


# =============================
#  Shop Image Upload (SAFE)
# =============================
def shop_image_upload(instance, filename):
    name, ext = os.path.splitext(filename)
    safe_name = slugify(name)

    #  prevent overwrite using UUID
    unique_name = f"{safe_name}-{uuid.uuid4().hex[:6]}"

    return f"shops/{unique_name}{ext}"


# =============================
#  Shop Model
# =============================
class Shop(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    description = models.TextField()
    image = models.ImageField(upload_to=shop_image_upload, null=True, blank=True)

    def __str__(self):
        return self.name


# =============================
#  Service Model
# =============================
class Service(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="services")
    name = models.CharField(max_length=100)
    price_per_kg = models.DecimalField(max_digits=6, decimal_places=2)

    def __str__(self):
        return f"{self.name} - {self.shop.name}"


# =============================
#  Order Model
# =============================
class Order(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="orders")
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE)
    service = models.ForeignKey(Service, on_delete=models.CASCADE)

    weight = models.DecimalField(max_digits=5, decimal_places=2)

    #  Money field
    total_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    #  Snapshot customer details
    customer_phone = models.CharField(max_length=15, blank=True, null=True)
    customer_location = models.CharField(max_length=255, blank=True, null=True)

    #  Payment
    payment_status = models.CharField(max_length=20, default="pending")

    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('washing', 'Washing'),
        ('completed', 'Completed'),
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        #  Calculate total price safely
        if self.service and self.weight:
            self.total_price = Decimal(self.service.price_per_kg) * Decimal(self.weight)

        #  Snapshot user details
        if self.user:
            self.customer_phone = self.user.phone
            self.customer_location = self.user.location

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.service.name} ({self.status})"














