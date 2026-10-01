from rest_framework import serializers
from .models import CashTransaction


class CashTransactionSerializer(serializers.ModelSerializer):
    signed_amount = serializers.ReadOnlyField()
    supplier_name = serializers.CharField(source="supplier.name", read_only=True, default=None)

    class Meta:
        model = CashTransaction
        fields = [
            "id", "type", "amount", "signed_amount", "method", "description",
            "repair", "supplier", "supplier_name", "expense_category", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def create(self, validated_data):
        request = self.context["request"]
        validated_data["shop"] = request.user.shop
        validated_data["branch"] = request.user.branch
        validated_data["created_by"] = request.user
        return super().create(validated_data)
