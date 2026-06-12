from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django import forms

from .models import User, Shop, Service, Order


# ===============================
# 🔐 CUSTOM USER FORMS
# ===============================
class CustomUserCreationForm(UserCreationForm):
    """
    Form for creating new users in admin.
    Ensures password is properly hashed on creation.
    """
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email", "username", "role", "phone", "location")


class CustomUserChangeForm(UserChangeForm):
    """
    Form for editing existing users in admin.
    Ensures password is properly hashed on update.
    """
    class Meta(UserChangeForm.Meta):
        model = User
        fields = ("email", "username", "role", "phone", "location")


# ===============================
# 👤 USER ADMIN
# ===============================
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Extends Django's built-in UserAdmin so password hashing,
    password change form, and permission management all work
    correctly with our custom User model.
    """

    form = CustomUserChangeForm
    add_form = CustomUserCreationForm

    list_display = (
        "id",
        "username",
        "email",
        "role",
        "is_staff",
        "is_active",
    )

    list_filter = ("role", "is_staff", "is_active")
    search_fields = ("username", "email")
    ordering = ("id",)

    # Fields shown when editing an existing user
    fieldsets = (
        (None, {
            "fields": ("email", "username", "password")
        }),
        ("Personal Info", {
            "fields": ("phone", "location")
        }),
        ("Role & Permissions", {
            "fields": (
                "role",
                "is_active",
                "is_staff",
                "is_superuser",
                "groups",
                "user_permissions",
            )
        }),
        ("Important Dates", {
            "fields": ("last_login", "date_joined")
        }),
    )

    # Fields shown when creating a new user
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "email",
                "username",
                "role",
                "phone",
                "location",
                "password1",
                "password2",
                "is_staff",
                "is_active",
            ),
        }),
    )


# ===============================
# 🏪 SHOP ADMIN
# ===============================
@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "owner", "location")
    list_filter = ("owner",)
    search_fields = ("name", "location", "owner__username")
    ordering = ("id",)


# ===============================
# 🧺 SERVICE ADMIN
# ===============================
@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "shop", "price_per_kg")
    list_filter = ("shop",)
    search_fields = ("name", "shop__name")
    ordering = ("id",)


# ===============================
# 📦 ORDER ADMIN
# ===============================
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "shop",
        "service",
        "weight",
        "total_price",
        "status",
        "created_at",
    )
    list_filter = ("status", "shop")
    search_fields = ("user__username", "user__email", "shop__name")
    ordering = ("-created_at",)