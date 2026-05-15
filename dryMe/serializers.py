from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Shop, Service, Order

User = get_user_model()


# ===============================
# 🔐 Register Serializer
# ===============================
class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    phone = serializers.CharField(required=False, allow_blank=True)
    location = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'password', 'role', 'phone', 'location')

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            password=validated_data['password'],
            role=validated_data.get('role', 'customer'),
            phone=validated_data.get('phone', ''),
            location=validated_data.get('location', ''),
        )
        return user


# ===============================
# 👤 User Serializer
# ===============================
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'role')


# ===============================
# 🏪 Shop Serializer
# ===============================
from rest_framework import serializers
from .models import Shop, Service, Order
from django.contrib.auth import get_user_model

User = get_user_model()


# ===============================
# 🏪 SHOP SERIALIZER
# ===============================
class ShopSerializer(serializers.ModelSerializer):
    owner = serializers.ReadOnlyField(source='owner.username')
    image = serializers.SerializerMethodField()

    class Meta:
        model = Shop
        fields = (
            'id',
            'owner',
            'name',
            'location',
            'description',
            'image'
        )

    def get_image(self, obj):
        request = self.context.get("request")

        if obj.image:
            try:
                return request.build_absolute_uri(obj.image.url)
            except:
                return None

        return None


# class ShopSerializer(serializers.ModelSerializer):

#     owner = serializers.ReadOnlyField(
#         source='owner.username'
#     )

#     image = serializers.SerializerMethodField()

#     class Meta:
#         model = Shop
#         fields = (
#             'id',
#             'owner',
#             'name',
#             'location',
#             'description',
#             'image',
#         )

# def get_image(self, obj):
#     request = self.context.get("request")

#     if obj.image:
#         if request:
#             url = request.build_absolute_uri(obj.image.url)
#             return url.replace("http://", "https://")
#         return obj.image.url

#     return None

    # def get_image(self, obj):

    #     request = self.context.get("request")

    #     if obj.image:

    #         if request:
    #             return request.build_absolute_uri(
    #                 obj.image.url
    #             )

    #         return obj.image.url

    #     return None

# # ===============================
# # 🏪 Shop Serializer
# # ===============================
# class ShopSerializer(serializers.ModelSerializer):
#     owner = serializers.ReadOnlyField(source='owner.username')

#     class Meta:
#         model = Shop
#         fields = ('id', 'owner', 'name', 'location', 'description', 'image')


# ===============================
# 🧺 Service Serializer
# ===============================
class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ('id', 'name', 'price_per_kg', 'shop')  # ✅ include shop


# ===============================
# 📦 Order Serializer
# ===============================
class OrderSerializer(serializers.ModelSerializer):

    # ✅ Read (what frontend receives)
    user = UserSerializer(read_only=True)
    shop = ShopSerializer(read_only=True)
    service = ServiceSerializer(read_only=True)

    # ✅ Write (what frontend sends)
    shop_id = serializers.PrimaryKeyRelatedField(
        queryset=Shop.objects.all(),
        source='shop',
        write_only=True
    )
    service_id = serializers.PrimaryKeyRelatedField(
        queryset=Service.objects.all(),
        source='service',
        write_only=True
    )

    # ✅ Customer snapshot fields
    customer_phone = serializers.CharField(read_only=True)
    customer_location = serializers.CharField(read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "user",
            "shop",
            "service",
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
        ]

    # ===========================
    # ✅ VALIDATION (SAFE)
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
    # ✅ CREATE ORDER
    # ===========================
    def create(self, validated_data):
        user = self.context["request"].user

        return Order.objects.create(
            user=user,
            shop=validated_data["shop"],
            service=validated_data["service"],
            weight=validated_data["weight"],
        )









# from rest_framework import serializers
# from .models import User, Shop, Service, Order
# from django.contrib.auth import get_user_model
# # from .serializers import UserSerializer, ShopSerializer, ServiceSerializer


# User = get_user_model()


# # -------------------------------
# # 🔐 Register user
# # -------------------------------

# from rest_framework import serializers
# from .models import User


# class RegisterSerializer(serializers.ModelSerializer):
#     password = serializers.CharField(write_only=True)

#     #  ADD THESE
#     phone = serializers.CharField(required=False, allow_blank=True)
#     location = serializers.CharField(required=False, allow_blank=True)

#     class Meta:
#         model = User
#         fields = ('id', 'username', 'password', 'role', 'phone', 'location')

#     def create(self, validated_data):
#         return User.objects.create_user(
#             username=validated_data['username'],
#             password=validated_data['password'],
#             role=validated_data.get('role', 'customer'),
#             phone=validated_data.get('phone'),
#             location=validated_data.get('location'),
#         )
# #
# # -------------------------------
# #  User serializer
# # -------------------------------
# class UserSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = User
#         fields = ('id', 'username', 'role')


# # -------------------------------
# #  Shop serializer
# # -------------------------------
# class ShopSerializer(serializers.ModelSerializer):
#     owner = serializers.ReadOnlyField(source='owner.username')

#     class Meta:
#         model = Shop
#         fields = ('id', 'owner', 'name', 'location', 'description', 'image')


# # -------------------------------
# #  Service serializer
# # -------------------------------
# class ServiceSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Service
#         fields = ('id', 'name', 'price_per_kg')


# # -------------------------------
# #  ORDER SERIALIZER (FINAL FIX)
# # -------------------------------

# class OrderSerializer(serializers.ModelSerializer):

#     # (what frontend receives)
#     user = UserSerializer(read_only=True)
#     shop = ShopSerializer(read_only=True)
#     service = ServiceSerializer(read_only=True)

#     # (what frontend sends)
#     shop_id = serializers.PrimaryKeyRelatedField(
#         queryset=Shop.objects.all(),
#         source='shop',
#         write_only=True
#     )
#     service_id = serializers.PrimaryKeyRelatedField(
#         queryset=Service.objects.all(),
#         source='service',
#         write_only=True
#     )

#     #  NEW: expose customer details
#     customer_phone = serializers.CharField(read_only=True)
#     customer_location = serializers.CharField(read_only=True)

#     class Meta:
#         model = Order
#         fields = [
#             "id",
#             "user",
#             "shop",
#             "service",
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
#         ]

#     #  VALIDATION
#     def validate(self, data):
#         if data["service"].shop != data["shop"]:
#             raise serializers.ValidationError(
#                 "Selected service does not belong to this shop"
#             )
#         return data

#     #  CREATE ORDER
#     def create(self, validated_data):
#         user = self.context["request"].user

#         return Order.objects.create(
#             user=user,
#             shop=validated_data["shop"],
#             service=validated_data["service"],
#             weight=validated_data["weight"],
#         )
# #