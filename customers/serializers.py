from rest_framework import serializers
from .models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    initials = serializers.ReadOnlyField()
    repair_count = serializers.SerializerMethodField()
    total_spent = serializers.SerializerMethodField()
    total_debt = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = ["id", "full_name", "phone", "email", "note", "initials",
                  "repair_count", "total_spent", "total_debt", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_repair_count(self, obj):
        return obj.repair_orders.exclude(status="cancelled").count()

    def get_total_spent(self, obj):
        return sum((r.sale_price for r in obj.repair_orders.exclude(status="cancelled")), 0)

    def get_total_debt(self, obj):
        # Müştərinin REAL borcu — təkcə artıq 'borc' (təhvil verilib, ödənilməyib) statusunda
        # olanlar yox, hələ təhvil verilməmiş (qismən ödənilmiş) sifarişlərin qalığı da daxildir.
        # Əks halda, məsələn, təmir prosesindəki bir sifarişə görə ödənilməmiş məbləğ heç vaxt
        # bura düşmürdü və göstərilən rəqəm real borcdan az görünürdü.
        return sum(
            (max(r.remaining_debt, 0) for r in obj.repair_orders.exclude(status="cancelled")),
            0,
        )