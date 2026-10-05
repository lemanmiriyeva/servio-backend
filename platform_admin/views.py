from decimal import Decimal
from django.db.models import Sum
from rest_framework import viewsets, status as http_status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.throttling import ScopedRateThrottle

from accounts.mixins import IsPlatformAdmin
from tenants.models import Shop
from .models import SupportTicket, SubscriptionPayment
from .serializers import SupportTicketSerializer, SubscriptionPaymentSerializer, ContactInquiryPublicSerializer
from .resources import RESOURCES, build_meta, _is_shop_admin


class SupportTicketViewSet(viewsets.ModelViewSet):
    queryset = SupportTicket.objects.select_related("shop").all()
    serializer_class = SupportTicketSerializer
    permission_classes = [IsAuthenticated, IsPlatformAdmin]


class ContactInquiryPublicCreateView(APIView):
    """
    POST /api/platform/public-contact/   { full_name, phone, message }
    İctimai sayt '/elaqe' formu — giriş TƏLƏB OLUNMUR, hər kəs göndərə bilər.
    Nəticə Baş Adminin panelində 'Müştəri sorğuları' bölməsinə düşür.
    """
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "contact"

    def post(self, request):
        s = ContactInquiryPublicSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        s.save()
        return Response({"detail": "Göndərildi."}, status=http_status.HTTP_201_CREATED)


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


class PlatformResourcesView(APIView):
    """
    GET /api/platform/resources/ — platforma panelindəki bölmələrin təsviri.
    Platform Super Admin: HAMISI. Mağaza sahibi (owner rolu): yalnız `shop_scoped=True`
    olanlar (öz mağazasının "Ətraflı" səhifəsindəki tab-lar) — imtiyazlı sahələr `build_meta`
    daxilində artıq gizlədilir.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if user.is_platform_admin or user.is_superuser:
            return Response([build_meta(r, request) for r in RESOURCES])
        if not _is_shop_admin(user):
            raise PermissionDenied("Bu bölməyə giriş icazəniz yoxdur.")
        return Response([build_meta(r, request) for r in RESOURCES if r.shop_scoped])