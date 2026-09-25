from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import SupportTicketViewSet, SubscriptionPaymentViewSet, PlatformDashboardView

router = DefaultRouter()
router.register("tickets", SupportTicketViewSet, basename="support-ticket")
router.register("payments", SubscriptionPaymentViewSet, basename="subscription-payment")
urlpatterns = router.urls + [
    path("dashboard/", PlatformDashboardView.as_view(), name="platform-dashboard"),
]
