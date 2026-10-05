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
        # Yaradıldıqdan sonra YALNIZ "düzəliş" sahələri (təsvir, üsul, kateqoriya) dəyişilə bilər.
        # "Məbləğ"/"Növ"/təmir-təchizatçı bağlantısı HEÇ VAXT redaktə yolu ilə dəyişmir — bunlar
        # başqa qeydlərin (RepairPayment, təchizatçı borc FIFO-su) əks nüsxəsidir; onları burada
        # dəyişmək həmin qeydlərlə kassanı sinxronsuz qoyardı. Məbləğ səhvdirsə, düzəliş YENİ
        # əməliyyat kimi aparılmalıdır.
        for locked in ("amount", "type", "repair", "supplier"):
            validated_data.pop(locked, None)
        return super().update(instance, validated_data)