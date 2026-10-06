from rest_framework import serializers
from repairs.models import RepairOrder
from .models import Supplier, SupplierPurchase, SupplierPurchasePayment


class SupplierPurchasePaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierPurchasePayment
        fields = ["id", "amount", "paid_at", "method"]


class SupplierPurchaseSerializer(serializers.ModelSerializer):
    remaining = serializers.ReadOnlyField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    repair = serializers.PrimaryKeyRelatedField(queryset=RepairOrder.objects.all(), required=False, allow_null=True)
    repair_number = serializers.CharField(source="repair.number", read_only=True, default=None)
    customer_name = serializers.CharField(source="repair.customer.full_name", read_only=True, default=None)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    payments = serializers.SerializerMethodField()

    class Meta:
        model = SupplierPurchase
        fields = ["id", "description", "amount", "paid_amount", "remaining", "purchased_at",
                  "status", "status_display",
                  "repair", "repair_number", "customer_name", "supplier", "supplier_name", "payments"]
        read_only_fields = ["id", "supplier", "status"]

    def get_payments(self, obj):
        rows = list(obj.payments.all())
        if not rows and obj.paid_amount:
            # Köhnə qeydlər (SupplierPurchasePayment yaradılmazdan əvvəl, məs. seed demo və ya
            # alışla birlikdə ilkin ödəniş) üçün — ən azı alışın özündəki məbləği göstər.
            return [{"id": None, "amount": obj.paid_amount, "paid_at": obj.purchased_at, "method": ""}]
        return SupplierPurchasePaymentSerializer(rows, many=True).data


class SupplierSerializer(serializers.ModelSerializer):
    purchases = SupplierPurchaseSerializer(many=True, read_only=True)
    total_purchased = serializers.ReadOnlyField()
    total_paid = serializers.ReadOnlyField()
    total_debt = serializers.ReadOnlyField()
    pending_returns = serializers.SerializerMethodField()

    class Meta:
        model = Supplier
        fields = ["id", "name", "phone", "note", "purchases",
                  "total_purchased", "total_paid", "total_debt", "pending_returns", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_pending_returns(self, obj):
        from repairs.models import RepairWarrantyReturn, SupplierReturnStatus
        from repairs.serializers import RepairWarrantyReturnSerializer
        qs = RepairWarrantyReturn.objects.filter(
            supplier_purchase__supplier=obj, supplier_status=SupplierReturnStatus.PENDING
        ).select_related("repair", "repair__customer", "supplier_purchase")
        return RepairWarrantyReturnSerializer(qs, many=True).data