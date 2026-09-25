from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from accounts.mixins import ShopScopedQuerysetMixin, HasModulePermission
from accounts.models import Module
from .models import Product, StockMovement
from .serializers import ProductSerializer, StockMovementSerializer


class ProductViewSet(ShopScopedQuerysetMixin, viewsets.ModelViewSet):
    """Yalnız ÖZ mağazanın anbarı."""
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated, HasModulePermission]
    module_code = Module.INVENTORY
    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "brand", "sku", "category"]


class StockMovementViewSet(ShopScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = StockMovement.objects.select_related("product").all()
    serializer_class = StockMovementSerializer
    permission_classes = [IsAuthenticated, HasModulePermission]
    module_code = Module.INVENTORY
