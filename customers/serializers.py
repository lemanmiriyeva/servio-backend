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
        return sum((r.remaining_debt for r in obj.repair_orders.filter(payment_status="debt")), 0)