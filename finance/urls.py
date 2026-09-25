from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import CashTransactionViewSet, CashboxSummaryView

router = DefaultRouter()
router.register("transactions", CashTransactionViewSet, basename="cash-transaction")
urlpatterns = router.urls + [
    path("summary/", CashboxSummaryView.as_view(), name="cashbox-summary"),
]
