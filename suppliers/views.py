from decimal import Decimal
from django.db import models
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from accounts.mixins import ShopScopedQuerysetMixin, HasModulePermission
from accounts.models import Module
from .models import Supplier
from .serializers import SupplierSerializer


class SupplierViewSet(ShopScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Supplier.objects.prefetch_related("purchases").all()
    serializer_class = SupplierSerializer
    permission_classes = [IsAuthenticated, HasModulePermission]
    module_code = Module.SUPPLIERS

    @action(detail=True, methods=["post"], url_path="pay")
    def pay(self, request, pk=None):
        """
        Təchizatçıya ödəniş — məbləği ən köhnə açıq alışlardan başlayaraq (FIFO) bağlayır
        və Kassaya 'Təchizatçı ödənişi' kimi çıxış yazır.
        """
        supplier = self.get_object()
        try:
            amount = Decimal(str(request.data.get("amount")))
        except Exception:
            return Response({"detail": "Məbləğ düzgün deyil."}, status=status.HTTP_400_BAD_REQUEST)
        if amount <= 0:
            return Response({"detail": "Məbləğ sıfırdan böyük olmalıdır."}, status=status.HTTP_400_BAD_REQUEST)

        remaining_to_apply = amount
        for purchase in supplier.purchases.filter(paid_amount__lt=models.F("amount")).order_by("purchased_at"):
            if remaining_to_apply <= 0:
                break
            owed = purchase.remaining
            applied = min(owed, remaining_to_apply)
            purchase.paid_amount += applied
            purchase.save(update_fields=["paid_amount"])
            remaining_to_apply -= applied

        from finance.models import CashTransaction, TransactionType
        CashTransaction.objects.create(
            shop=supplier.shop, type=TransactionType.SUPPLIER_PAYMENT,
            amount=amount - remaining_to_apply if remaining_to_apply > 0 else amount,
            method=request.data.get("method", "cash"),
            description=f"{supplier.name} — borc ödənişi",
            supplier=supplier, created_by=request.user,
        )
        # get_object()-in prefetch_related("purchases") keşi yuxarıdakı dəyişikliklərdən
        # sonra köhnəlmiş qalır — cavab üçün təzə obyekt oxuyuruq.
        fresh = self.get_queryset().get(pk=supplier.pk)
        return Response(SupplierSerializer(fresh).data)

    @action(detail=True, methods=["post"], url_path="purchases")
    def add_purchase(self, request, pk=None):
        supplier = self.get_object()
        from .serializers import SupplierPurchaseSerializer
        s = SupplierPurchaseSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        s.save(shop=supplier.shop, supplier=supplier)
        fresh = self.get_queryset().get(pk=supplier.pk)
        return Response(SupplierSerializer(fresh).data, status=status.HTTP_201_CREATED)