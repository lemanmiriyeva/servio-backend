from rest_framework import serializers
from customers.models import Customer
from customers.serializers import CustomerSerializer
from suppliers.models import SupplierPurchase, PurchaseStatus
from .models import (
    RepairOrder, RepairPayment, RepairStatus, RepairStatusHistory, RepairWarrantyReturn, SupplierReturnStatus,
)


class RepairPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = RepairPayment
        fields = ["id", "amount", "method", "paid_at"]
        read_only_fields = ["id", "paid_at"]


class RepairOrderListSerializer(serializers.ModelSerializer):
    """Siyahı/dashboard üçün yüngül forma."""
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    customer_initials = serializers.CharField(source="customer.initials", read_only=True)
    warranty_days_left = serializers.ReadOnlyField()
    remaining_debt = serializers.ReadOnlyField()
    last_status_at = serializers.ReadOnlyField()

    class Meta:
        model = RepairOrder
        fields = [
            "id", "number", "customer", "customer_name", "customer_initials",
            "device_brand", "device_model", "issue_description",
            "status", "payment_status", "sale_price", "remaining_debt",
            "warranty_days_left", "received_at", "delivered_at", "last_status_at",
        ]


class RepairWarrantyReturnSerializer(serializers.ModelSerializer):
    repair_number = serializers.CharField(source="repair.number", read_only=True)
    customer_name = serializers.CharField(source="repair.customer.full_name", read_only=True)
    supplier_id = serializers.SerializerMethodField()
    supplier_name = serializers.SerializerMethodField()
    part_description = serializers.SerializerMethodField()

    class Meta:
        model = RepairWarrantyReturn
        fields = [
            "id", "repair", "repair_number", "customer_name", "reason",
            "refund_amount", "supplier_purchase", "supplier_id", "supplier_name",
            "part_description", "return_amount", "supplier_status", "supplier_note",
            "supplier_resolved_at", "created_at",
        ]
        read_only_fields = fields

    def get_supplier_id(self, obj):
        return obj.supplier_purchase.supplier_id if obj.supplier_purchase_id else None

    def get_supplier_name(self, obj):
        return obj.supplier_purchase.supplier.name if obj.supplier_purchase_id else None

    def get_part_description(self, obj):
        return obj.supplier_purchase.description if obj.supplier_purchase_id else None


class WarrantyReturnCreateSerializer(serializers.Serializer):
    reason = serializers.CharField()
    refund_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0)
    supplier_purchase_id = serializers.PrimaryKeyRelatedField(
        source="supplier_purchase", queryset=SupplierPurchase.objects.all(), required=False, allow_null=True
    )
    return_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0)
    send_to_supplier = serializers.BooleanField(required=False, default=True)

    def validate_supplier_purchase(self, sp):
        request = self.context["request"]
        if sp is not None and sp.shop_id != request.user.shop_id:
            raise serializers.ValidationError("Bu alış sizin mağazaya aid deyil.")
        return sp

    def save(self, **kwargs):
        request = self.context["request"]
        repair: RepairOrder = self.context["repair"]
        data = self.validated_data
        supplier_purchase = data.get("supplier_purchase")
        return_amount = data.get("return_amount") or (supplier_purchase.amount if supplier_purchase else 0)

        wr = RepairWarrantyReturn.objects.create(
            shop=repair.shop, repair=repair,
            reason=data["reason"],
            refund_amount=data.get("refund_amount") or 0,
            supplier_purchase=supplier_purchase,
            return_amount=return_amount,
            created_by=request.user,
        )
        if wr.refund_amount and wr.refund_amount > 0:
            from finance.models import CashTransaction, TransactionType
            CashTransaction.objects.create(
                shop=repair.shop, branch=repair.branch, type=TransactionType.REFUND,
                amount=wr.refund_amount, method="cash",
                description=f"{repair.number}, {repair.customer.full_name} — zəmanət qaytarması",
                repair=repair, created_by=request.user,
            )
        if data.get("send_to_supplier", True) and wr.supplier_purchase_id:
            wr.send_to_supplier()
        return wr


class SupplierReturnDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=[SupplierReturnStatus.ACCEPTED, SupplierReturnStatus.REJECTED])
    note = serializers.CharField(required=False, allow_blank=True, default="")

    def save(self, **kwargs):
        wr: RepairWarrantyReturn = self.context["warranty_return"]
        wr.resolve_supplier(self.validated_data["decision"], self.validated_data.get("note", ""))
        return wr


class RepairStatusHistorySerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = RepairStatusHistory
        fields = ["status", "status_display", "changed_at"]


class RepairOrderDetailSerializer(serializers.ModelSerializer):
    customer = CustomerSerializer(read_only=True)
    customer_id = serializers.PrimaryKeyRelatedField(
        source="customer", queryset=Customer.objects.all(), write_only=True
    )
    payments = RepairPaymentSerializer(many=True, read_only=True)
    supplier_purchases = serializers.SerializerMethodField()
    warranty_returns = RepairWarrantyReturnSerializer(many=True, read_only=True)
    status_history = RepairStatusHistorySerializer(many=True, read_only=True)
    paid_amount = serializers.ReadOnlyField()
    remaining_debt = serializers.ReadOnlyField()
    profit = serializers.ReadOnlyField()
    warranty_end_date = serializers.ReadOnlyField()
    warranty_days_left = serializers.ReadOnlyField()

    class Meta:
        model = RepairOrder
        fields = [
            "id", "number", "customer", "customer_id",
            "device_brand", "device_model", "device_imei", "device_serial", "accessories_note",
            "technician_name",
            "issue_description", "work_done_note",
            "cost_price", "sale_price", "profit",
            "status", "payment_status", "debt_due_date",
            "warranty_days", "warranty_started_at", "warranty_end_date", "warranty_days_left",
            "received_at", "delivered_at",
            "payments", "supplier_purchases", "warranty_returns", "status_history",
            "paid_amount", "remaining_debt",
            "created_at",
        ]
        read_only_fields = ["id", "number", "created_at"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and not user.has_module_permission("revenue_numbers"):
            # Maya və qazanc — 'Gəlir / net mənfəət rəqəmləri' icazəsi olmayan rola görünmür
            data["cost_price"] = None
            data["profit"] = None
            data["supplier_purchases"] = []
            for wr in data.get("warranty_returns", []):
                wr["return_amount"] = None
        return data

    def get_supplier_purchases(self, obj):
        return [
            {"id": p.id, "supplier": p.supplier.name, "description": p.description,
             "amount": p.amount, "paid_amount": p.paid_amount,
             # Ləğv edilmiş alış üçün "qalıq borc" artıq göstərilmir (0) — təmir ləğv
             # ediləndə bu alış da ləğv olunur və ümumi təchizatçı borcundan çıxır
             # (bax Supplier.total_debt), ona görə burda da borc kimi görünməməlidir.
             "remaining": 0 if p.status == PurchaseStatus.CANCELLED else p.remaining,
             "status": p.status, "status_display": p.get_status_display()}
            for p in obj.supplier_purchases.select_related("supplier").all()
        ]

    def create(self, validated_data):
        request = self.context["request"]
        validated_data["shop"] = request.user.shop
        validated_data["branch"] = request.user.branch
        validated_data["created_by"] = request.user
        return super().create(validated_data)


class RepairStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=RepairStatus.choices)

    def save(self, **kwargs):
        from django.utils import timezone
        repair: RepairOrder = self.context["repair"]
        new_status = self.validated_data["status"]
        old_status = repair.status
        changed = new_status != old_status
        repair.status = new_status
        if new_status == RepairStatus.DELIVERED and not repair.delivered_at:
            repair.delivered_at = timezone.now()
            repair.warranty_started_at = timezone.now().date()
        repair.save()
        if changed and new_status == RepairStatus.CANCELLED:
            # Təmir ləğv edilir — ona bağlı təchizatçı alışları da "ləğv edildi" kimi işarələnir
            # (silinmir, tarixçədə qalır), ümumi təchizatçı borcundan isə çıxır.
            from suppliers.models import PurchaseStatus
            repair.supplier_purchases.update(status=PurchaseStatus.CANCELLED)
            # Bu təmirə görə müştəridən artıq real pul alınıbsa (kassaya "Kassa"/gəlir kimi
            # düşübsə), ləğv edəndə onu silmirik (maliyyə tarixçəsi qorunur), əvəzinə eyni
            # məbləğdə "Geri qaytarma" qeydi əlavə edirik ki, Kassa balansı özü-özünə düzəlsin —
            # müştəri "ləğv etdim, amma kassada qalır" şikayəti elə bunun üçün idi.
            from finance.models import CashTransaction, TransactionType
            net_received = sum(
                (t.amount if t.type == TransactionType.INCOME else -t.amount)
                for t in CashTransaction.objects.filter(
                    repair=repair, type__in=[TransactionType.INCOME, TransactionType.REFUND]
                )
            )
            if net_received > 0:
                request = self.context.get("request")
                CashTransaction.objects.create(
                    shop=repair.shop, branch=repair.branch, type=TransactionType.REFUND,
                    amount=net_received, method="cash",
                    description=f"{repair.number}, {repair.customer.full_name} — xidmət ləğv edildi, ödəniş geri qaytarıldı",
                    repair=repair, created_by=getattr(request, "user", None),
                )
        elif changed and old_status == RepairStatus.CANCELLED:
            # Ləğv edilmiş təmir yenidən aktivləşdirilirsə, bağlı alışlar da geri aktivləşir
            # və maya dəyəri yenidən onların cəminə görə hesablanır.
            from suppliers.models import PurchaseStatus, sync_repair_cost_price
            repair.supplier_purchases.filter(status=PurchaseStatus.CANCELLED).update(status=PurchaseStatus.ACTIVE)
            sync_repair_cost_price(repair)
        if changed:
            # Hər status dəyişikliyinin vaxtı qeydə alınır ("nə vaxtdan təmir prosesindədir",
            # "nə vaxtdan hazırdır" və s. sualları üçün — bax RepairStatusHistory).
            RepairStatusHistory.objects.create(repair=repair, status=new_status)
        # Status dəyişəndə (xüsusən 'Təhvil verildi'-yə keçəndə) ödəniş statusunu
        # yenidən hesabla — qalıq borc varsa indi 'debt' kimi işarələnəcək.
        repair.recompute_payment_status()
        return repair


class RepairPaymentCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    method = serializers.ChoiceField(choices=RepairPayment._meta.get_field("method").choices)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Məbləğ sıfırdan böyük olmalıdır.")
        repair: RepairOrder = self.context["repair"]
        remaining = repair.remaining_debt
        if remaining > 0 and value > remaining:
            raise serializers.ValidationError(
                f"Ödəniş qalıq borcdan ({remaining} AZN) çox ola bilməz."
            )
        return value

    def save(self, **kwargs):
        repair: RepairOrder = self.context["repair"]
        request = self.context["request"]
        payment = RepairPayment.objects.create(
            repair=repair, amount=self.validated_data["amount"],
            method=self.validated_data["method"], received_by=request.user,
        )
        from finance.models import CashTransaction, TransactionType
        CashTransaction.objects.create(
            shop=repair.shop, branch=repair.branch, type=TransactionType.INCOME,
            amount=payment.amount, method=payment.method,
            description=f"{repair.number}, {repair.customer.full_name}",
            repair=repair, created_by=request.user,
        )
        # repair.payments queryset ola bilsin artıq keşlənib (məs. viewset-in
        # prefetch_related-i vasitəsilə) — yuxarıdakı create() bu keşi yeniləmir,
        # ona görə borcu düzgün hesablamaq üçün keşi təmizləyirik.
        if hasattr(repair, "_prefetched_objects_cache"):
            repair._prefetched_objects_cache.pop("payments", None)
        repair.recompute_payment_status()
        return payment