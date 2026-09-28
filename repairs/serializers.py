from rest_framework import serializers
from customers.models import Customer
from customers.serializers import CustomerSerializer
from .models import RepairOrder, RepairPayment, RepairStatus


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

    class Meta:
        model = RepairOrder
        fields = [
            "id", "number", "customer", "customer_name", "customer_initials",
            "device_brand", "device_model", "issue_description",
            "status", "payment_status", "sale_price", "remaining_debt",
            "warranty_days_left", "received_at", "delivered_at",
        ]


class RepairOrderDetailSerializer(serializers.ModelSerializer):
    customer = CustomerSerializer(read_only=True)
    customer_id = serializers.PrimaryKeyRelatedField(
        source="customer", queryset=Customer.objects.all(), write_only=True
    )
    payments = RepairPaymentSerializer(many=True, read_only=True)
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
            "issue_description", "work_done_note",
            "cost_price", "sale_price", "profit",
            "status", "payment_status", "debt_due_date",
            "warranty_days", "warranty_started_at", "warranty_end_date", "warranty_days_left",
            "received_at", "delivered_at",
            "payments", "paid_amount", "remaining_debt",
            "created_at",
        ]
        read_only_fields = ["id", "number", "created_at"]

    def create(self, validated_data):
        request = self.context["request"]
        validated_data["shop"] = request.user.shop
        validated_data["branch"] = request.user.branch
        validated_data["created_by"] = request.user
        return super().create(validated_data)


class RepairStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=RepairStatus.choices)

    def save(self, **kwargs):
        repair: RepairOrder = self.context["repair"]
        new_status = self.validated_data["status"]
        repair.status = new_status
        if new_status == RepairStatus.DELIVERED and not repair.delivered_at:
            from django.utils import timezone
            repair.delivered_at = timezone.now()
            repair.warranty_started_at = timezone.now().date()
        repair.save()
        # Status dəyişəndə (xüsusən 'Təhvil verildi'-yə keçəndə) ödəniş statusunu
        # yenidən hesabla — qalıq borc varsa indi 'debt' kimi işarələnəcək.
        repair.recompute_payment_status()
        return repair


class RepairPaymentCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    method = serializers.ChoiceField(choices=RepairPayment._meta.get_field("method").choices)

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