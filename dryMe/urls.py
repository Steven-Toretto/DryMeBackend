from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

from .views import (
    RegisterView,
    LoginView,
    ShopListCreateView,
    ShopDetailView,
    ServiceListCreateView,
    OrderListCreateView,
    OwnerOrderListView,
    UpdateOrderStatusView,
    ArchiveOrderView,
    ArchivedOrdersView,
    featured_shops,
    create_superuser,
)

urlpatterns = [

    # 🔐 AUTH
    path(
        'register/',
        RegisterView.as_view()
    ),

    path(
        'login/',
        LoginView.as_view()
    ),

    # 🏪 SHOPS
    path(
        'shops/',
        ShopListCreateView.as_view()
    ),

    path(
        'shops/<int:pk>/',
        ShopDetailView.as_view()
    ),

    # ⭐ FEATURED SHOPS (PUBLIC)
    path(
        'featured-shops/',
        featured_shops
    ),

    # 🧺 SERVICES
    path(
        'services/',
        ServiceListCreateView.as_view()
    ),

    # 📦 CUSTOMER ORDERS
    path(
        'orders/',
        OrderListCreateView.as_view()
    ),

    # ✅ ARCHIVED ORDERS — must come BEFORE orders/<int:pk>/
    path(
        'orders/archived/',
        ArchivedOrdersView.as_view()
    ),

    # 🔄 UPDATE ORDER STATUS
    path(
        'orders/<int:pk>/status/',
        UpdateOrderStatusView.as_view()
    ),

    # 📁 ARCHIVE ORDER
    path(
        'orders/<int:pk>/archive/',
        ArchiveOrderView.as_view()
    ),

    # 📦 OWNER ORDERS
    path(
        'owner/orders/',
        OwnerOrderListView.as_view()
    ),

    # ✅ OWNER ARCHIVED ORDERS — must come BEFORE owner/orders/<int:pk>/
    path(
        'owner/orders/archived/',
        ArchivedOrdersView.as_view()
    ),
    path('create-superuser/', create_superuser),

]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )