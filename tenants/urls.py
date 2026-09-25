from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import ShopViewSet, PlanViewSet, MyShopSettingsView, BranchViewSet

router = DefaultRouter()
router.register("shops", ShopViewSet, basename="platform-shop")
router.register("plans", PlanViewSet, basename="plan")
router.register("branches", BranchViewSet, basename="branch")
urlpatterns = router.urls + [
    path("my-shop/", MyShopSettingsView.as_view(), name="my-shop-settings"),
]
