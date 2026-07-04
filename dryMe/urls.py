from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

from .views import (
    RegisterView,
    LoginView,
    ShopListCreateView,
    ShopDetailView,
    ServiceListCreateView,
    ServiceDetailView,
    OrderListCreateView,
    OwnerOrderListView,
    UpdateOrderStatusView,
    DeclineOrderView,
    CancelOrderView,
    UpdateOrderNotesView,
    ArchiveOrderView,
    ArchivedOrdersView,
    MpesaSTKPushView,
    PaymentStatusView,
    mpesa_callback,
    featured_shops,
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

    # 🧺 SERVICE DETAIL (EDIT + DELETE)
    path(
        'services/<int:pk>/',
        ServiceDetailView.as_view()
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

    # ❌ DECLINE ORDER (requires reason)
    path(
        'orders/<int:pk>/decline/',
        DeclineOrderView.as_view()
    ),

    # 🚫 CANCEL ORDER (customer)
    path(
        'orders/<int:pk>/cancel/',
        CancelOrderView.as_view()
    ),

    # 📝 UPDATE ORDER NOTES
    path(
        'orders/<int:pk>/notes/',
        UpdateOrderNotesView.as_view()
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

    # 💳 MPESA PAYMENTS
    path(
        'orders/<int:order_id>/pay/',
        MpesaSTKPushView.as_view()
    ),

    path(
        'orders/<int:order_id>/payment-status/',
        PaymentStatusView.as_view()
    ),

    path(
        'mpesa/callback/',
        mpesa_callback
    ),

    # ✅ OWNER ARCHIVED ORDERS — must come BEFORE owner/orders/<int:pk>/
    path(
        'owner/orders/archived/',
        ArchivedOrdersView.as_view()
    ),

    

]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )