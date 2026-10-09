from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db.models import Avg

from .models import Shop, Service, Order, Review, Notification

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
# 👤 PROFILE SERIALIZER
# ===============================
class ProfileSerializer(serializers.ModelSerializer):

    class Meta:
        model = User

        fields = (
            "id",
            "username",
            "email",
            "role",
            "phone",
            "location",
            "date_joined",
        )

        read_only_fields = (
            "id",
            "email",
            "role",
            "date_joined",
        )

    def validate_username(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Username can't be empty.")
        return value

    def validate_phone(self, value):
        if value and len(value.strip()) > 15:
            raise serializers.ValidationError("Phone number is too long.")
        return value.strip() if value else value

    def validate_location(self, value):
        if value and len(value.strip()) > 255:
            raise serializers.ValidationError("Location is too long.")
        return value.strip() if value else value


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

    lat = serializers.FloatField(required=False, allow_null=True)
    lng = serializers.FloatField(required=False, allow_null=True)

    average_rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()

    def get_average_rating(self, obj):
        avg = obj.reviews.aggregate(avg=Avg("rating"))["avg"]
        return round(avg, 1) if avg is not None else None

    def get_review_count(self, obj):
        return obj.reviews.count()

    class Meta:
        model = Shop

        fields = (
            "id",
            "owner",
            "name",
            "location",
            "description",
            "image",
            "lat",
            "lng",
            "average_rating",
            "review_count",
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
            "price",
            "pricing_type",
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

    # Whether the customer has already left a review for this order —
    # lets the frontend show "Rate this order" vs. the existing rating
    # without a separate lookup.
    has_review = serializers.SerializerMethodField()

    def get_has_review(self, obj):
        return hasattr(obj, "review")

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
    # WEIGHT / QUANTITY — exactly one is required, depending on the
    # selected service's pricing_type. Enforced in validate() below,
    # since the right answer depends on which service was picked.
    # ===========================
    weight = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        allow_null=True,
    )
    quantity = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
    )

    # ===========================
    # SNAPSHOT FIELDS — writable so the customer can confirm/override
    # per order at checkout, instead of silently relying on whatever
    # (if anything) is saved on their profile.
    # ===========================
    customer_phone = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=15,
        error_messages={
            "blank": "A phone number is required so the shop can reach you.",
            "required": "A phone number is required so the shop can reach you.",
        },
    )
    customer_location = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=255,
        error_messages={
            "blank": "A pickup location is required.",
            "required": "A pickup location is required.",
        },
    )
    customer_notes = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    # 📍 Optional exact GPS pin — not required, since not every browser/
    # device will grant location permission. customer_location (text)
    # remains the required fallback.
    pickup_lat = serializers.FloatField(
        required=False,
        allow_null=True,
    )
    pickup_lng = serializers.FloatField(
        required=False,
        allow_null=True,
    )

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

    # ===========================
    # TIMELINE FIELDS
    # ===========================
    confirmed_at = serializers.DateTimeField(read_only=True)
    washing_at = serializers.DateTimeField(read_only=True)
    completed_at = serializers.DateTimeField(read_only=True)
    declined_at = serializers.DateTimeField(read_only=True)
    cancelled_at = serializers.DateTimeField(read_only=True)

    # ===========================
    # DECLINE FIELDS
    # ===========================
    decline_reason = serializers.CharField(read_only=True)
    refund_needed = serializers.BooleanField(read_only=True)

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
            "quantity",
            "total_price",
            "status",

            # SNAPSHOT
            "customer_phone",
            "customer_location",
            "customer_notes",
            "pickup_lat",
            "pickup_lng",

            # ARCHIVE
            "customer_archived",
            "owner_archived",

            # PAYMENT
            "payment_status",
            "mpesa_transaction_code",

            # DECLINE
            "decline_reason",
            "refund_needed",

            # TIMELINE
            "created_at",
            "confirmed_at",
            "washing_at",
            "completed_at",
            "declined_at",
            "cancelled_at",

            # REVIEW
            "has_review",
        ]

        read_only_fields = [
            "user",
            "total_price",
            "status",
            "customer_archived",
            "owner_archived",
            "payment_status",
            "mpesa_transaction_code",
            "decline_reason",
            "refund_needed",
            "created_at",
            "confirmed_at",
            "washing_at",
            "completed_at",
            "declined_at",
            "cancelled_at",
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
    # VALIDATE — weight vs quantity depends on the chosen service
    # ===========================
    def validate(self, attrs):
        service = attrs.get("service")

        if service:
            if service.pricing_type == "per_item":
                if not attrs.get("quantity"):
                    raise serializers.ValidationError({
                        "quantity": "This service is priced per item — specify how many.",
                    })
            elif service.pricing_type == "per_kg":
                if not attrs.get("weight"):
                    raise serializers.ValidationError({
                        "weight": "This service is priced by weight — specify how much.",
                    })

        return attrs

    # ===========================
    # CREATE ORDER
    # ===========================
    def create(self, validated_data):

        user = self.context["request"].user

        pickup_lat = validated_data.get("pickup_lat")
        pickup_lng = validated_data.get("pickup_lng")

        order = Order.objects.create(
            user=user,
            shop=validated_data["shop"],
            service=validated_data["service"],
            weight=validated_data.get("weight"),
            quantity=validated_data.get("quantity"),
            customer_notes=validated_data.get("customer_notes", ""),
            customer_phone=validated_data.get("customer_phone", ""),
            customer_location=validated_data.get("customer_location", ""),
            # Round here rather than trust the client — GPS coordinates
            # routinely arrive with far more precision than the DB
            # column allows (max_digits=9, decimal_places=6).
            pickup_lat=round(pickup_lat, 6) if pickup_lat is not None else None,
            pickup_lng=round(pickup_lng, 6) if pickup_lng is not None else None,
        )

        return order


# ===============================
# ⭐ REVIEW SERIALIZER
# ===============================
class ReviewSerializer(serializers.ModelSerializer):

    username = serializers.CharField(
        source="user.username",
        read_only=True,
    )

    class Meta:
        model = Review

        fields = (
            "id",
            "shop",
            "order",
            "username",
            "rating",
            "comment",
            "created_at",
        )

        read_only_fields = (
            "id",
            "shop",
            "order",
            "username",
            "created_at",
        )

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value

    def validate_comment(self, value):
        if value and len(value) > 1000:
            raise serializers.ValidationError("Comment is too long.")
        return value


# ===============================
# 🔔 NOTIFICATION SERIALIZER
# ===============================
class NotificationSerializer(serializers.ModelSerializer):

    class Meta:
        model = Notification

        fields = (
            "id",
            "notif_type",
            "message",
            "order",
            "review",
            "is_read",
            "created_at",
        )

        read_only_fields = fields

        