from rest_framework import viewsets, filters, mixins
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


class StockMovementViewSet(ShopScopedQuerysetMixin, mixins.CreateModelMixin, mixins.ListModelMixin,
                            mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Anbar hərəkətləri dəyişməz jurnal qeydləridir: yaratmaq və oxumaq olar, silinmir/redaktə olunmur."""
    queryset = StockMovement.objects.select_related("product").all()
    serializer_class = StockMovementSerializer
    permission_classes = [IsAuthenticated, HasModulePermission]
    module_code = Module.INVENTORY