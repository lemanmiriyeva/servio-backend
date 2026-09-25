from rest_framework import serializers
from .models import Supplier, SupplierPurchase


class SupplierPurchaseSerializer(serializers.ModelSerializer):
    remaining = serializers.ReadOnlyField()

    class Meta:
        model = SupplierPurchase
        fields = ["id", "description", "amount", "paid_amount", "remaining", "purchased_at"]
        read_only_fields = ["id"]


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
