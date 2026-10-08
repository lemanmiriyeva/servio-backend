from rest_framework import viewsets, generics, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q

from accounts.mixins import HasModulePermission
from accounts.models import Module
from inventory.models import Product
from .models import MarketplaceOrder, OrderStatus
from .serializers import MarketplaceProductSearchSerializer, MarketplaceOrderSerializer


class MarketplaceSearchView(generics.ListAPIView):
    """
    GET /api/marketplace/search/?q=ekran
    Bütün mağazalar üzrə YALNIZ paylaşıma açıq məhsulları göstərir (öz mağazan xaric).
    Maya dəyəri heç vaxt göstərilmir.
    """
    serializer_class = MarketplaceProductSearchSerializer
    permission_classes = [IsAuthenticated, HasModulePermission]
    module_code = Module.MARKETPLACE
    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "brand", "category"]

    def get_queryset(self):
        user = self.request.user
        qs = Product.objects.filter(is_shared_to_marketplace=True, quantity_in_stock__gt=0)
        if user.shop_id:
            qs = qs.exclude(shop_id=user.shop_id)
        return qs.select_related("shop")


class MarketplaceOrderViewSet(viewsets.ModelViewSet):
    """
    Bir istifadəçi HƏM alıcı, HƏM satıcı tərəf kimi görünə bilər —
    ona görə ShopScopedQuerysetMixin İSTİFADƏ OLUNMUR, xüsusi filtr yazılır.
    """
    serializer_class = MarketplaceOrderSerializer
    permission_classes = [IsAuthenticated, HasModulePermission]
    module_code = Module.MARKETPLACE

    def get_queryset(self):
        shop_id = self.request.user.shop_id
        return (MarketplaceOrder.objects.filter(Q(buyer_shop_id=shop_id) | Q(seller_shop_id=shop_id))
                .select_related("product", "buyer_shop", "seller_shop"))

    @staticmethod
    def _require_seller(request, order):
        # Əvvəllər bu yoxlama heç yerdə yox idi — alıcı öz sifarişini özü "qəbul edə",
        # "ödənildi" yaza, hətta "göndərildi" işarələyə bilirdi. Qəbul/rədd/ödəniş/göndərmə
        # yalnız SATICI tərəfin işidir.
        if request.user.shop_id != order.seller_shop_id:
            raise PermissionDenied("Bu əməliyyatı yalnız satıcı tərəf edə bilər.")

    @staticmethod
    def _require_buyer(request, order):
        if request.user.shop_id != order.buyer_shop_id:
            raise PermissionDenied("Bu əməliyyatı yalnız alıcı tərəf edə bilər.")

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        order = self.get_object()
        self._require_seller(request, order)
        order.accept()
        return Response(MarketplaceOrderSerializer(order).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        order = self.get_object()
        self._require_seller(request, order)
        order.reject(note=request.data.get("note", ""))
        return Response(MarketplaceOrderSerializer(order).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()
        # Ləğvetmə alıcının öz fikrindən daşınmasıdır — satıcı sifarişi "rədd et"
        # əməliyyatı ilə geri çevirir, "ləğv et" ilə yox.
        self._require_buyer(request, order)
        order.cancel()
        return Response(MarketplaceOrderSerializer(order).data)

    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid(self, request, pk=None):
        order = self.get_object()
        self._require_seller(request, order)
        order.mark_paid()
        return Response(MarketplaceOrderSerializer(order).data)

    @action(detail=True, methods=["post"], url_path="mark-shipped")
    def mark_shipped(self, request, pk=None):
        order = self.get_object()
        self._require_seller(request, order)
        order.mark_shipped()
        return Response(MarketplaceOrderSerializer(order).data)

    @action(detail=True, methods=["post"], url_path="mark-completed")
    def mark_completed(self, request, pk=None):
        order = self.get_object()
        # Təhvil aldığını təsdiqləmək alıcının işidir — anbarına da elə buna görə əlavə olunur.
        self._require_buyer(request, order)
        order.mark_completed()
        return Response(MarketplaceOrderSerializer(order).data)