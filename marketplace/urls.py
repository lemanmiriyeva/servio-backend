from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import MarketplaceOrderViewSet, MarketplaceSearchView

router = DefaultRouter()
router.register("orders", MarketplaceOrderViewSet, basename="marketplace-order")
urlpatterns = router.urls + [
    path("search/", MarketplaceSearchView.as_view(), name="marketplace-search"),
]
