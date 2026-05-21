from django.urls import path

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

    # 🧺 SERVICES
    path(
        'services/',
        ServiceListCreateView.as_view()
    ),

    # 📦 ORDERS
    path(
        'orders/',
        OrderListCreateView.as_view()
    ),

    path(
        'owner/orders/',
        OwnerOrderListView.as_view()
    ),

    # 🔄 UPDATE STATUS
    path(
        'orders/<int:pk>/status/',
        UpdateOrderStatusView.as_view()
    ),

    # 📁 ARCHIVE ORDER
    path(
        'orders/<int:pk>/archive/',
        ArchiveOrderView.as_view()
    ),

    # 📁 GET ARCHIVED ORDERS
    path(
        'orders/archived/',
        ArchivedOrdersView.as_view()
    ),

    # ⭐ FEATURED SHOPS
    path(
        'featured-shops/',
        featured_shops
    ),
]



# from django.urls import path

# from .views import (
#     RegisterView,
#     LoginView,

#     # Shops
#     ShopListCreateView,
#     ShopDetailView,

#     # Services
#     ServiceListCreateView,

#     # Orders
#     OrderListCreateView,
#     OwnerOrderListView,
#     UpdateOrderStatusView,
#     ArchiveOrderView,
#     ArchivedOrdersView,

#     # Featured
#     featured_shops,
# )

# urlpatterns = [

#     # =========================
#     # 🔐 AUTH
#     # =========================
#     path(
#         "register/",
#         RegisterView.as_view()
#     ),

#     path(
#         "login/",
#         LoginView.as_view()
#     ),

#     # =========================
#     # 🏪 SHOPS
#     # =========================
#     path(
#         "shops/",
#         ShopListCreateView.as_view()
#     ),

#     path(
#         "shops/<int:pk>/",
#         ShopDetailView.as_view()
#     ),

#     # =========================
#     # 🧺 SERVICES
#     # =========================
#     path(
#         "services/",
#         ServiceListCreateView.as_view()
#     ),

#     # =========================
#     # 📦 ORDERS
#     # =========================
#     path(
#         "orders/",
#         OrderListCreateView.as_view()
#     ),

#     path(
#         "owner/orders/",
#         OwnerOrderListView.as_view()
#     ),

#     path(
#         "orders/<int:pk>/status/",
#         UpdateOrderStatusView.as_view()
#     ),

#     # =========================
#     # 📁 ARCHIVE ORDERS
#     # =========================

#     # Archive single completed order
#     path(
#         "orders/<int:pk>/archive/",
#         ArchiveOrderView.as_view()
#     ),

#     # Get archived orders
#     path(
#         "archived-orders/",
#         ArchivedOrdersView.as_view()
#     ),

#     # =========================
#     # ⭐ FEATURED SHOPS
#     # =========================
#     path(
#         "featured-shops/",
#         featured_shops
#     ),
# ]


