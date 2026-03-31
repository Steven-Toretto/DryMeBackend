from django.urls import path
from .views import (
    RegisterView,
    LoginView,
    ShopListCreateView,
    ShopDetailView,  # ✅ ADD THIS
    ServiceListCreateView,
    OrderListCreateView,
    OwnerOrderListView,
    UpdateOrderStatusView,
    featured_shops,  # ✅ move here
)

urlpatterns = [
    # 🔐 Auth
    path('register/', RegisterView.as_view()),
    path('login/', LoginView.as_view()),

    # 🏪 Shops
    path('shops/', ShopListCreateView.as_view()),
    path('shops/<int:pk>/', ShopDetailView.as_view()),  # ✅ IMPORTANT (edit/delete)

    # 🧺 Services
    path('services/', ServiceListCreateView.as_view()),

    # 📦 Orders
    path('orders/', OrderListCreateView.as_view()),
    path('owner/orders/', OwnerOrderListView.as_view()),
    path('orders/<int:pk>/status/', UpdateOrderStatusView.as_view()),

    # ⭐ Featured
    path('featured-shops/', featured_shops),
]    














# from django.urls import path
# from .views import (
#     RegisterView,
#     LoginView,
#     ShopListCreateView,
#     ServiceListCreateView,   # ✅ NOW EXISTS
#     OrderListCreateView,
#     OwnerOrderListView,
#     UpdateOrderStatusView,
  
    
# )
# from .views import featured_shops


# urlpatterns = [
#     path('register/', RegisterView.as_view()),
#     path('login/', LoginView.as_view()),

#     path('shops/', ShopListCreateView.as_view()),
#     path('services/', ServiceListCreateView.as_view()),

#     path('orders/', OrderListCreateView.as_view()),
#     path('owner/orders/', OwnerOrderListView.as_view()),
#     path('orders/<int:pk>/status/', UpdateOrderStatusView.as_view()),
#     path('featured-shops/', featured_shops),
    
 

# ]


