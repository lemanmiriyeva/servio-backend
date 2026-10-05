from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    SupportTicketViewSet, SubscriptionPaymentViewSet, PlatformDashboardView, PlatformResourcesView,
    ContactInquiryPublicCreateView,
)
from .resources import RESOURCES, build_viewset

router = DefaultRouter()
router.register("tickets", SupportTicketViewSet, basename="support-ticket")
router.register("payments", SubscriptionPaymentViewSet, basename="subscription-payment")

# Generik CRUD: /api/platform/r/<resurs>/   (mağazalar, istifadəçilər, rollar, ... hamısı)
generic = DefaultRouter()
for _res in RESOURCES:
    generic.register(rf"r/{_res.key}", build_viewset(_res), basename=f"pf-{_res.key}")

urlpatterns = router.urls + generic.urls + [
    path("dashboard/", PlatformDashboardView.as_view(), name="platform-dashboard"),
    path("resources/", PlatformResourcesView.as_view(), name="platform-resources"),
    # İctimai sayt — giriş tələb olunmur (bax: ContactInquiryPublicCreateView).
    path("public-contact/", ContactInquiryPublicCreateView.as_view(), name="public-contact"),
]