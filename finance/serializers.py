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

    def update(self, instance, validated_data):
        # "Növ"/təmir-təchizatçı bağlantısı HEÇ VAXT redaktə yolu ilə dəyişmir.
        # "Məbləğ" isə YALNIZ bu qeyd bir təmirə/təchizatçıya bağlı DEYİLSƏ redaktə olunur —
        # bağlı olan qeydlər (RepairPayment, təchizatçı borc FIFO-su) başqa yerin əks nüsxəsidir;
        # onların məbləğini burada dəyişmək həmin qeydlərlə kassanı sinxronsuz qoyardı.
        for locked in ("type", "repair", "supplier"):
            validated_data.pop(locked, None)
        if instance.repair_id or instance.supplier_id:
            validated_data.pop("amount", None)
        return super().update(instance, validated_data)