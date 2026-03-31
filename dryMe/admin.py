from django.contrib import admin
from .models import User, Shop, Service, Order

# ----------------------------
# Custom User Admin
# ----------------------------
@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('id', 'username', 'email', 'role', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_active')
    search_fields = ('username', 'email')
    ordering = ('id',)


# ----------------------------
# Shop Admin
# ----------------------------
@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'owner', 'location')
    list_filter = ('owner',)
    search_fields = ('name', 'location', 'owner__username')
    ordering = ('id',)


# ----------------------------
# Service Admin
# ----------------------------
@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'shop', 'price_per_kg')
    list_filter = ('shop',)
    search_fields = ('name', 'shop__name')
    ordering = ('id',)


# ----------------------------
# Order Admin
# ----------------------------
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "shop",
        "service",
        "weight",
        "total_price",  # ✅ FIXED HERE
        "status",
        "created_at",
    )
    
  