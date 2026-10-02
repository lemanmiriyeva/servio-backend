from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import ShopViewSet, PlanViewSet, MyShopSettingsView, BranchViewSet, SupportTicketViewSet

router = DefaultRouter()
router.register("shops", ShopViewSet, basename="platform-shop")
router.register("plans", PlanViewSet, basename="plan")
router.register("branches", BranchViewSet, basename="branch")
router.register("support-tickets", SupportTicketViewSet, basename="support-ticket")
urlpatterns = router.urls + [
    path("my-shop/", MyShopSettingsView.as_view(), name="my-shop-settings"),
]