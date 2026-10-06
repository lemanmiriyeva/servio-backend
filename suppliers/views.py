from decimal import Decimal
from django.db import models
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from accounts.mixins import ShopScopedQuerysetMixin, HasModulePermission
from accounts.models import Module
from .models import Supplier, SupplierPurchasePayment, sync_repair_cost_price
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

    @action(detail=True, methods=["patch"], url_path=r"purchases/(?P<purchase_id>\d+)")
    def update_purchase(self, request, pk=None, purchase_id=None):
        """
        PATCH /api/suppliers/<id>/purchases/<purchase_id>/   { description, amount }
        Təsvir həmişə sərbəst redaktə olunur. Məbləğ də redaktə oluna bilər, amma artıq
        ödənilmiş hissədən AZ ola bilməz (FIFO ödəniş bölgüsü əlavə ödənilmiş məbləğə
        əsaslanıb tətbiq olunub — onu "geri götürmək" mümkün deyil, sadəcə qalıq borcu
        (amount - paid_amount) düzgün saxlamalıyıq).
        """
        supplier = self.get_object()
        purchase = supplier.purchases.filter(pk=purchase_id).first()
        if not purchase:
            return Response({"detail": "Alış tapılmadı."}, status=status.HTTP_404_NOT_FOUND)
        description = request.data.get("description")
        update_fields = []
        if description is not None and description.strip():
            purchase.description = description.strip()
            update_fields.append("description")
        if request.data.get("amount") is not None:
            try:
                amount = Decimal(str(request.data.get("amount")))
            except Exception:
                return Response({"detail": "Məbləğ düzgün deyil."}, status=status.HTTP_400_BAD_REQUEST)
            if amount <= 0:
                return Response({"detail": "Məbləğ sıfırdan böyük olmalıdır."}, status=status.HTTP_400_BAD_REQUEST)
            if amount < purchase.paid_amount:
                return Response(
                    {"detail": f"Məbləğ artıq ödənilmiş {purchase.paid_amount} AZN-dən az ola bilməz."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            purchase.amount = amount
            update_fields.append("amount")
        if update_fields:
            purchase.save(update_fields=update_fields)
            if "amount" in update_fields and purchase.repair_id:
                sync_repair_cost_price(purchase.repair)
        fresh = self.get_queryset().get(pk=supplier.pk)
        return Response(SupplierSerializer(fresh).data)

    @action(detail=True, methods=["patch"], url_path=r"purchases/(?P<purchase_id>\d+)/payments/(?P<payment_id>\d+)")
    def update_purchase_payment(self, request, pk=None, purchase_id=None, payment_id=None):
        """
        PATCH /api/suppliers/<id>/purchases/<purchase_id>/payments/<payment_id>/   { amount }
        Konkret bir ödəniş qeydinin məbləğini düzəldir (məs. səhv yazılıb). Alışın
        `paid_amount`-u da fərqə görə (yeni - köhnə) uyğunlaşdırılır, 0 ilə alışın
        ümumi məbləği arasında qalmaq şərtilə.
        """
        supplier = self.get_object()
        purchase = supplier.purchases.filter(pk=purchase_id).first()
        if not purchase:
            return Response({"detail": "Alış tapılmadı."}, status=status.HTTP_404_NOT_FOUND)
        payment = purchase.payments.filter(pk=payment_id).first()
        if not payment:
            return Response({"detail": "Ödəniş tapılmadı."}, status=status.HTTP_404_NOT_FOUND)
        try:
            new_amount = Decimal(str(request.data.get("amount")))
        except Exception:
            return Response({"detail": "Məbləğ düzgün deyil."}, status=status.HTTP_400_BAD_REQUEST)
        if new_amount <= 0:
            return Response({"detail": "Məbləğ sıfırdan böyük olmalıdır."}, status=status.HTTP_400_BAD_REQUEST)

        delta = new_amount - payment.amount
        new_paid_amount = purchase.paid_amount + delta
        if new_paid_amount < 0 or new_paid_amount > purchase.amount:
            return Response(
                {"detail": f"Bu dəyişiklik alışın ödənilmiş məbləğini 0–{purchase.amount} AZN "
                            f"aralığından kənara çıxarır."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payment.amount = new_amount
        payment.save(update_fields=["amount"])
        purchase.paid_amount = new_paid_amount
        purchase.save(update_fields=["paid_amount"])

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
        if purchase.repair_id:
            sync_repair_cost_price(purchase.repair)
        fresh = self.get_queryset().get(pk=supplier.pk)
        return Response(SupplierSerializer(fresh).data, status=status.HTTP_201_CREATED)