from rest_framework import serializers
from .models import Shop, Branch, Plan


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ["id", "name", "price_monthly", "max_branches", "max_users"]


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ["id", "name", "address", "phone", "is_main", "created_at"]
        read_only_fields = ["id", "created_at"]


class ShopSerializer(serializers.ModelSerializer):
    """Platform Super Admin üçün — '12 Platforma — Mağazalar' cədvəli."""
    plan = PlanSerializer(read_only=True)
    plan_id = serializers.PrimaryKeyRelatedField(source="plan", queryset=Plan.objects.all(),
                                                  write_only=True, required=False, allow_null=True)
    branch_count = serializers.IntegerField(source="branches.count", read_only=True)
    user_count = serializers.IntegerField(source="users.count", read_only=True)

    class Meta:
        model = Shop
        fields = [
            "id", "name", "code", "owner_full_name", "owner_phone", "owner_email", "city",
            "logo_initials", "plan", "plan_id", "status", "trial_ends_at", "next_payment_at",
            "default_warranty_days", "currency", "branch_count", "user_count", "created_at",
            "address", "phone", "work_hours", "tax_id", "receipt_terms",
        ]
        read_only_fields = ["id", "code", "logo_initials", "created_at"]


class ShopSettingsSerializer(serializers.ModelSerializer):
    """Mağaza öz Parametrlər səhifəsində YALNIZ bunları dəyişə bilər."""
    class Meta:
        model = Shop
        fields = ["name", "owner_full_name", "owner_phone", "owner_email", "city",
                  "default_warranty_days", "currency",
                  "address", "phone", "work_hours", "tax_id", "receipt_terms"]