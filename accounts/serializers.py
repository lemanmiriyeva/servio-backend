from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model

from tenants.models import Shop, Branch
from .models import Role, RolePermission, Module

User = get_user_model()


class ShopMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shop
        fields = ["id", "name", "code", "city", "currency", "default_warranty_days", "status"]


class BranchMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ["id", "name", "address", "is_main"]


class RolePermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RolePermission
        fields = ["module", "is_allowed"]


class RoleSerializer(serializers.ModelSerializer):
    permissions = RolePermissionSerializer(many=True, read_only=True)

    class Meta:
        model = Role
        fields = ["id", "name", "is_owner_role", "permissions"]


class MeSerializer(serializers.ModelSerializer):
    shop = ShopMiniSerializer(read_only=True)
    branch = BranchMiniSerializer(read_only=True)
    role = RoleSerializer(read_only=True)
    initials = serializers.ReadOnlyField()
    allowed_modules = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "first_name", "last_name", "email", "phone",
            "shop", "branch", "role", "initials", "is_platform_admin", "status",
            "allowed_modules",
        ]

    def get_allowed_modules(self, obj):
        if obj.is_platform_admin or obj.is_superuser:
            return list(Module.values)
        if not obj.role_id:
            return []
        if obj.role.is_owner_role:
            return list(Module.values)
        return list(obj.role.permissions.filter(is_allowed=True).values_list("module", flat=True))


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Login zamanı istifadəçi adı 'elvin.techfix' formatındadır (istifadəçi.mağaza-kodu)."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["shop_id"] = str(user.shop_id) if user.shop_id else None
        token["is_platform_admin"] = user.is_platform_admin
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = MeSerializer(self.user).data
        return data
