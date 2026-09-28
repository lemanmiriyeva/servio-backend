from rest_framework import serializers
from repairs.models import RepairOrder
from .models import Supplier, SupplierPurchase


class SupplierPurchaseSerializer(serializers.ModelSerializer):
    remaining = serializers.ReadOnlyField()
    repair = serializers.PrimaryKeyRelatedField(queryset=RepairOrder.objects.all(), required=False, allow_null=True)
    repair_number = serializers.CharField(source="repair.number", read_only=True, default=None)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)

    class Meta:
        model = SupplierPurchase
        fields = ["id", "description", "amount", "paid_amount", "remaining", "purchased_at",
                  "repair", "repair_number", "supplier", "supplier_name"]
        read_only_fields = ["id", "supplier"]


class SupplierSerializer(serializers.ModelSerializer):
    purchases = SupplierPurchaseSerializer(many=True, read_only=True)
    total_purchased = serializers.ReadOnlyField()
    total_paid = serializers.ReadOnlyField()
    total_debt = serializers.ReadOnlyField()

    class Meta:
        model = Supplier
        fields = ["id", "name", "phone", "note", "purchases",
                  "total_purchased", "total_paid", "total_debt", "created_at"]
        read_only_fields = ["id", "created_at"]