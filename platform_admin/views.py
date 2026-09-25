from decimal import Decimal
from django.db.models import Sum
from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from accounts.mixins import IsPlatformAdmin
from tenants.models import Shop
from .models import SupportTicket, SubscriptionPayment
from .serializers import SupportTicketSerializer, SubscriptionPaymentSerializer


class SupportTicketViewSet(viewsets.ModelViewSet):
    queryset = SupportTicket.objects.select_related("shop").all()
    serializer_class = SupportTicketSerializer
    permission_classes = [IsAuthenticated, IsPlatformAdmin]


class SubscriptionPaymentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SubscriptionPayment.objects.select_related("shop").all()
    serializer_class = SubscriptionPaymentSerializer
    permission_classes = [IsAuthenticated, IsPlatformAdmin]


class PlatformDashboardView(APIView):
    """'12 Platforma — Mağazalar' səhifəsinin üst KPI kartları."""
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        shops = Shop.objects.all()
        active = shops.filter(status=Shop.Status.ACTIVE)
        trial = shops.filter(status=Shop.Status.TRIAL)
        mrr = active.aggregate(s=Sum("plan__price_monthly"))["s"] or Decimal("0")

        return Response({
            "total_shops": shops.count(),
            "active_count": active.count(),
            "trial_count": trial.count(),
            "overdue_count": shops.filter(status=Shop.Status.OVERDUE).count(),
            "blocked_count": shops.filter(status=Shop.Status.BLOCKED).count(),
            "mrr": mrr,
            "open_tickets": SupportTicket.objects.filter(status=SupportTicket.Status.OPEN).count(),
        })
