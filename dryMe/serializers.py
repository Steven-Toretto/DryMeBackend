from rest_framework import serializers
from django.contrib.auth import get_user_model

from .models import Shop, Service, Order

User = get_user_model()


# ===============================
# 🔐 REGISTER SERIALIZER
# ===============================
class RegisterSerializer(serializers.ModelSerializer):

    password = serializers.CharField(
        write_only=True
    )

    email = serializers.EmailField(
        required=True,
    )

    phone = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    location = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    class Meta:
        model = User

        fields = (
            "id",
            "username",
            "email",
            "password",
            "role",
            "phone",
            "location",
        )

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                "An account with this email already exists."
            )
        return value

    def create(self, validated_data):

        email = validated_data["email"]

        user = User.objects.create_user(
            email,
            password=validated_data["password"],
        )

        user.email = email
        user.username = validated_data["username"]
        user.role = validated_data.get("role", "customer")
        user.phone = validated_data.get("phone", "")
        user.location = validated_data.get("location", "")
        user.save()

        return user


# ===============================
# 👤 USER SERIALIZER
# ===============================
class UserSerializer(serializers.ModelSerializer):

    class Meta:
        model = User

        fields = (
            "id",
            "username",
            "role",
        )


# ===============================
# 🏪 SHOP SERIALIZER
# ===============================
class ShopSerializer(serializers.ModelSerializer):

    owner = serializers.CharField(
        source="owner.username",
        read_only=True
    )

    image = serializers.ImageField(
        required=False,
        allow_null=True
    )

    class Meta:
        model = Shop

        fields = (
            "id",
            "owner",
            "name",
            "location",
            "description",
            "image",
        )

    def to_representation(self, instance):

        representation = super().to_representation(instance)
        request = self.context.get("request")

        if instance.image:
            try:
                image_url = instance.image.url

                if image_url.startswith("http"):
                    representation["image"] = image_url
                elif request:
                    representation["image"] = (
                        request.build_absolute_uri(image_url)
                    )
                else:
                    representation["image"] = image_url

            except Exception:
                representation["image"] = None

        return representation


# ===============================
# 🧺 SERVICE SERIALIZER
# ===============================
class ServiceSerializer(serializers.ModelSerializer):

    class Meta:
        model = Service

        fields = (
            "id",
            "name",
            "price_per_kg",
            "shop",
        )


# ===============================
# 📦 ORDER SERIALIZER
# ===============================
class OrderSerializer(serializers.ModelSerializer):

    # ===========================
    # READ FIELDS
    # ===========================
    user = UserSerializer(read_only=True)
    shop = ShopSerializer(read_only=True)
    service = ServiceSerializer(read_only=True)

    # ===========================
    # WRITE FIELDS
    # ===========================
    shop_id = serializers.PrimaryKeyRelatedField(
        queryset=Shop.objects.all(),
        source="shop",
        write_only=True
    )

    service_id = serializers.PrimaryKeyRelatedField(
        queryset=Service.objects.all(),
        source="service",
        write_only=True
    )

    # ===========================
    # SNAPSHOT FIELDS
    # ===========================
    customer_phone = serializers.CharField(read_only=True)
    customer_location = serializers.CharField(read_only=True)

    # ===========================
    # ARCHIVE FIELDS
    # ===========================
    customer_archived = serializers.BooleanField(read_only=True)
    owner_archived = serializers.BooleanField(read_only=True)

    # ===========================
    # PAYMENT FIELDS
    # ===========================
    payment_status = serializers.CharField(read_only=True)
    mpesa_transaction_code = serializers.CharField(read_only=True)

    class Meta:
        model = Order

        fields = [
            "id",

            # READ
            "user",
            "shop",
            "service",

            # WRITE
            "shop_id",
            "service_id",

            "weight",
            "total_price",
            "status",

            # SNAPSHOT
            "customer_phone",
            "customer_location",

            # ARCHIVE
            "customer_archived",
            "owner_archived",

            # PAYMENT
            "payment_status",
            "mpesa_transaction_code",

            "created_at",
        ]

        read_only_fields = [
            "user",
            "total_price",
            "status",
            "customer_phone",
            "customer_location",
            "customer_archived",
            "owner_archived",
            "payment_status",
            "mpesa_transaction_code",
            "created_at",
        ]

    # ===========================
    # VALIDATE WEIGHT
    # ===========================
    def validate_weight(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Weight must be greater than 0."
            )
        return value

    # ===========================
    # VALIDATE SERVICE BELONGS TO SHOP
    # ===========================
    def validate(self, data):

        shop = data.get("shop")
        service = data.get("service")

        if shop and service:
            if service.shop != shop:
                raise serializers.ValidationError(
                    "Selected service does not belong to this shop"
                )

        return data

    # ===========================
    # CREATE ORDER
    # ===========================
    def create(self, validated_data):

        user = self.context["request"].user

        order = Order.objects.create(
            user=user,
            shop=validated_data["shop"],
            service=validated_data["service"],
            weight=validated_data["weight"],
        )

        return order