from decimal import Decimal
from django.db import models
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from accounts.mixins import ShopScopedQuerysetMixin, HasModulePermission
from accounts.models import Module
from .models import Supplier, SupplierPurchasePayment
from .serializers import SupplierSerializer


class SupplierViewSet(ShopScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Supplier.objects.prefetch_related("purchases").all()
    serializer_class = SupplierSerializer
    permission_classes = [IsAuthenticated, HasModulePermission]
    module_code = Module.SUPPLIERS
    # Ad/telefon üzrə axtarış — ?search=... (əvvəllər heç bir axtarış yox idi).
    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "phone"]

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

        method = request.data.get("method", "cash")
        remaining_to_apply = amount
        for purchase in supplier.purchases.filter(paid_amount__lt=models.F("amount")).order_by("purchased_at"):
            if remaining_to_apply <= 0:
                break
            owed = purchase.remaining
            applied = min(owed, remaining_to_apply)
            purchase.paid_amount += applied
            purchase.save(update_fields=["paid_amount"])
            # Bu alışın öz "hansı tarixdə nə qədər ödənilib" tarixçəsi üçün — bir ödəniş
            # bir neçə alışa bölünə bilər (FIFO), ona görə hər paya ayrı qeyd yaradılır.
            SupplierPurchasePayment.objects.create(purchase=purchase, amount=applied, method=method)
            remaining_to_apply -= applied

        from finance.models import CashTransaction, TransactionType
        CashTransaction.objects.create(
            shop=supplier.shop, type=TransactionType.SUPPLIER_PAYMENT,
            amount=amount - remaining_to_apply if remaining_to_apply > 0 else amount,
            method=method,
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
        repair = s.validated_data.get("repair")
        if repair is not None and repair.shop_id != supplier.shop_id:
            return Response({"detail": "Bu təmir sizin mağazaya aid deyil."}, status=status.HTTP_400_BAD_REQUEST)
        if s.validated_data.get("paid_amount", 0) > s.validated_data["amount"]:
            return Response({"detail": "Ödənilən məbləğ alış məbləğindən çox ola bilməz."}, status=status.HTTP_400_BAD_REQUEST)
        purchase = s.save(shop=supplier.shop, supplier=supplier)
        if purchase.paid_amount:
            SupplierPurchasePayment.objects.create(purchase=purchase, amount=purchase.paid_amount, method="cash")
        fresh = self.get_queryset().get(pk=supplier.pk)
        return Response(SupplierSerializer(fresh).data, status=status.HTTP_201_CREATED)