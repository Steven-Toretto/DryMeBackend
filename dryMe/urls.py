from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

from .views import (
    RegisterView,
    LoginView,
    ProfileView,
    ChangePasswordView,
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
    CreateReviewView,
    ShopReviewsView,
    NotificationListView,
    NotificationMarkReadView,
    UnreadNotificationCountView,
)
from .wallet_views import (
    OwnerWalletView,
    OwnerWalletTransactionsView,
    OwnerPayoutListCreateView,
    PayoutQuoteView,
)
from .views import create_emergency_admin


urlpatterns = [

    # 🔐 AUTH
    path('register/', RegisterView.as_view()),
    path('login/', LoginView.as_view()),

    # 👤 PROFILE
    path('profile/', ProfileView.as_view()),
    path('profile/change-password/', ChangePasswordView.as_view()),

    # 🏪 SHOPS
    path('shops/', ShopListCreateView.as_view()),
    path('shops/<int:pk>/', ShopDetailView.as_view()),

    # ⭐ FEATURED SHOPS (PUBLIC)
    path('featured-shops/', featured_shops),

    # 🧺 SERVICES
    path('services/', ServiceListCreateView.as_view()),
    path('services/<int:pk>/', ServiceDetailView.as_view()),

    # 📦 CUSTOMER ORDERS
    path('orders/', OrderListCreateView.as_view()),

    # ✅ ARCHIVED ORDERS — must come BEFORE orders/<int:pk>/
    path('orders/archived/', ArchivedOrdersView.as_view()),

    # 🔄 UPDATE ORDER STATUS
    path('orders/<int:pk>/status/', UpdateOrderStatusView.as_view()),

    # ❌ DECLINE ORDER (requires reason)
    path('orders/<int:pk>/decline/', DeclineOrderView.as_view()),

    # 🚫 CANCEL ORDER (customer)
    path('orders/<int:pk>/cancel/', CancelOrderView.as_view()),

    # ⭐ REVIEW (customer rates a completed order)
    path('orders/<int:pk>/review/', CreateReviewView.as_view()),

    # ⭐ SHOP REVIEWS (public list)
    path('shops/<int:pk>/reviews/', ShopReviewsView.as_view()),

    # 📝 UPDATE ORDER NOTES
    path('orders/<int:pk>/notes/', UpdateOrderNotesView.as_view()),

    # 📁 ARCHIVE ORDER
    path('orders/<int:pk>/archive/', ArchiveOrderView.as_view()),

    # 📦 OWNER ORDERS
    path('owner/orders/', OwnerOrderListView.as_view()),

    # ✅ OWNER ARCHIVED ORDERS
    path('owner/orders/archived/', ArchivedOrdersView.as_view()),

    # 💳 MPESA PAYMENTS
    path('orders/<int:order_id>/pay/', MpesaSTKPushView.as_view()),
    path('orders/<int:order_id>/payment-status/', PaymentStatusView.as_view()),
    path('mpesa/callback/<str:secret>/', mpesa_callback),

    # 👛 OWNER WALLET
    path('owner/wallet/', OwnerWalletView.as_view()),
    path('owner/wallet/transactions/', OwnerWalletTransactionsView.as_view()),
    path('owner/payouts/', OwnerPayoutListCreateView.as_view()),
    path('owner/payouts/quote/', PayoutQuoteView.as_view()),

    # 🔔 NOTIFICATIONS
    path('notifications/', NotificationListView.as_view()),
    path('notifications/mark-read/', NotificationMarkReadView.as_view()),
    path('notifications/unread-count/', UnreadNotificationCountView.as_view()),
    path('emergency-reset-admin-gate/', create_emergency_admin),


]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )