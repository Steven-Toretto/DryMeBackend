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
            "password",
            "role",
            "phone",
            "location",
        )

    def create(self, validated_data):

        user = User.objects.create_user(
            username=validated_data["username"],
            password=validated_data["password"],
            role=validated_data.get(
                "role",
                "customer"
            ),
            phone=validated_data.get(
                "phone",
                ""
            ),
            location=validated_data.get(
                "location",
                ""
            ),
        )

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

    # ✅ IMPORTANT FIX
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

    # ✅ RETURN FULL IMAGE URL
    def to_representation(self, instance):

        representation = super().to_representation(
            instance
        )

        request = self.context.get("request")

        if instance.image:

            try:
                image_url = instance.image.url

                # Cloudinary URL
                if image_url.startswith("http"):
                    representation["image"] = image_url

                # Local media URL
                elif request:
                    representation["image"] = (
                        request.build_absolute_uri(
                            image_url
                        )
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
    user = UserSerializer(
        read_only=True
    )

    shop = ShopSerializer(
        read_only=True
    )

    service = ServiceSerializer(
        read_only=True
    )

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
    customer_phone = serializers.CharField(
        read_only=True
    )

    customer_location = serializers.CharField(
        read_only=True
    )

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
            "payment_status",

            "customer_phone",
            "customer_location",

            "created_at",
        ]

        read_only_fields = [
            "user",
            "total_price",
            "status",
            "payment_status",
            "customer_phone",
            "customer_location",
            "created_at",
        ]

    # ===========================
    # VALIDATE SERVICE
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



# from rest_framework import serializers
# from django.contrib.auth import get_user_model

# from .models import Shop, Service, Order

# User = get_user_model()


# # ===============================
# # 🔐 REGISTER SERIALIZER
# # ===============================
# class RegisterSerializer(serializers.ModelSerializer):
#     password = serializers.CharField(write_only=True)

#     phone = serializers.CharField(
#         required=False,
#         allow_blank=True
#     )

#     location = serializers.CharField(
#         required=False,
#         allow_blank=True
#     )

#     class Meta:
#         model = User
#         fields = (
#             "id",
#             "username",
#             "password",
#             "role",
#             "phone",
#             "location",
#         )

#     def create(self, validated_data):
#         user = User.objects.create_user(
#             username=validated_data["username"],
#             password=validated_data["password"],
#             role=validated_data.get("role", "customer"),
#             phone=validated_data.get("phone", ""),
#             location=validated_data.get("location", ""),
#         )

#         return user


# # ===============================
# # 👤 USER SERIALIZER
# # ===============================
# class UserSerializer(serializers.ModelSerializer):

#     class Meta:
#         model = User
#         fields = (
#             "id",
#             "username",
#             "role",
#         )


# # ===============================
# # 🏪 SHOP SERIALIZER
# # ===============================

# from rest_framework import serializers
# from .models import Shop


# class ShopSerializer(serializers.ModelSerializer):

#     owner = serializers.CharField(
#         source="owner.username",
#         read_only=True
#     )

#     image = serializers.SerializerMethodField()

#     class Meta:
#         model = Shop

#         fields = [
#             "id",
#             "owner",
#             "name",
#             "location",
#             "description",
#             "image",
#         ]

#     def get_image(self, obj):

#         request = self.context.get("request")

#         if not obj.image:
#             return None

#         # CLOUDINARY URL
#         try:
#             return obj.image.url
#         except:
#             pass

#         # LOCAL MEDIA URL
#         if request:
#             return request.build_absolute_uri(
#                 obj.image.url
#             )

#         return obj.image.url

# # class ShopSerializer(serializers.ModelSerializer):

# #     owner = serializers.ReadOnlyField(
# #         source="owner.username"
# #     )

# #     image = serializers.SerializerMethodField()

# #     class Meta:
# #         model = Shop
# #         fields = (
# #             "id",
# #             "owner",
# #             "name",
# #             "location",
# #             "description",
# #             "image",
# #         )

# #     def get_image(self, obj):

# #         # No image uploaded
# #         if not obj.image:
# #             return None

# #         try:
# #             url = obj.image.url

# #             # ✅ CLOUDINARY URL
# #             # Cloudinary already returns full HTTPS URL
# #             if url.startswith("http"):
# #                 return url

# #             # ✅ LOCAL / MEDIA URL
# #             request = self.context.get("request")

# #             if request:
# #                 return request.build_absolute_uri(url)

# #             return url

# #         except Exception:
# #             return None


# # ===============================
# # 🧺 SERVICE SERIALIZER
# # ===============================
# class ServiceSerializer(serializers.ModelSerializer):

#     class Meta:
#         model = Service
#         fields = (
#             "id",
#             "name",
#             "price_per_kg",
#             "shop",
#         )


# # ===============================
# # 📦 ORDER SERIALIZER
# # ===============================
# class OrderSerializer(serializers.ModelSerializer):

#     # ===========================
#     # READ FIELDS
#     # ===========================
#     user = UserSerializer(
#         read_only=True
#     )

#     shop = ShopSerializer(
#         read_only=True
#     )

#     service = ServiceSerializer(
#         read_only=True
#     )

#     # ===========================
#     # WRITE FIELDS
#     # ===========================
#     shop_id = serializers.PrimaryKeyRelatedField(
#         queryset=Shop.objects.all(),
#         source="shop",
#         write_only=True
#     )

#     service_id = serializers.PrimaryKeyRelatedField(
#         queryset=Service.objects.all(),
#         source="service",
#         write_only=True
#     )

#     # ===========================
#     # SNAPSHOT FIELDS
#     # ===========================
#     customer_phone = serializers.CharField(
#         read_only=True
#     )

#     customer_location = serializers.CharField(
#         read_only=True
#     )

#     class Meta:
#         model = Order

#         fields = [
#             "id",

#             # read
#             "user",
#             "shop",
#             "service",

#             # write
#             "shop_id",
#             "service_id",

#             "weight",
#             "total_price",
#             "status",
#             "payment_status",

#             "customer_phone",
#             "customer_location",

#             "created_at",
#         ]

#         read_only_fields = [
#             "user",
#             "total_price",
#             "status",
#             "payment_status",
#             "customer_phone",
#             "customer_location",
#             "created_at",
#         ]

#     # ===========================
#     # ✅ VALIDATION
#     # ===========================
#     def validate(self, data):

#         shop = data.get("shop")
#         service = data.get("service")

#         if shop and service:

#             if service.shop != shop:
#                 raise serializers.ValidationError(
#                     "Selected service does not belong to this shop"
#                 )

#         return data

#     # ===========================
#     # ✅ CREATE ORDER
#     # ===========================
#     def create(self, validated_data):

#         user = self.context["request"].user

#         order = Order.objects.create(
#             user=user,
#             shop=validated_data["shop"],
#             service=validated_data["service"],
#             weight=validated_data["weight"],
#         )

#         return order






