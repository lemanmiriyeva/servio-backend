from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from accounts.mixins import IsPlatformAdmin, ShopOwnQuerysetMixin
from .models import Shop, Branch, Plan
from .serializers import ShopSerializer, BranchSerializer, PlanSerializer, ShopSettingsSerializer


class ShopViewSet(viewsets.ModelViewSet):
    """Yalnız Platform Super Admin — '12 Platforma — Mağazalar' səhifəsi."""
    queryset = Shop.objects.select_related("plan").all()
    serializer_class = ShopSerializer
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["status", "plan"]
    search_fields = ["name", "code", "owner_full_name", "owner_phone", "city"]


class PlanViewSet(viewsets.ModelViewSet):
    queryset = Plan.objects.all()
    serializer_class = PlanSerializer
    permission_classes = [IsAuthenticated, IsPlatformAdmin]


class MyShopSettingsView(ShopOwnQuerysetMixin, APIView):
    """Adi mağaza admini üçün 'Parametrlər' səhifəsi — YALNIZ öz mağazasını görür/redaktə edir."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(ShopSettingsSerializer(self.get_object()).data)

    def patch(self, request):
        shop = self.get_object()
        s = ShopSettingsSerializer(shop, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)


class BranchViewSet(viewsets.ModelViewSet):
    """Mağaza öz filiallarını idarə edir (tenant-scoped)."""
    serializer_class = BranchSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_platform_admin or user.is_superuser:
            return Branch.objects.all()
        return Branch.objects.filter(shop_id=user.shop_id)

    def perform_create(self, serializer):
        serializer.save(shop=self.request.user.shop)
