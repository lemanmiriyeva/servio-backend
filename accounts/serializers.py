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
    user_count = serializers.IntegerField(source="users.count", read_only=True)

    class Meta:
        model = Role
        fields = ["id", "name", "is_owner_role", "permissions", "user_count"]
        read_only_fields = ["id", "is_owner_role"]


class SetPermissionsSerializer(serializers.Serializer):
    """PATCH /api/roles/{id}/permissions/ body: {"permissions": [{"module": "cashbox", "is_allowed": false}, ...]}"""
    permissions = RolePermissionSerializer(many=True)

    def save(self):
        role = self.context["role"]
        if role.is_owner_role:
            raise serializers.ValidationError("Sahib rolunun icazələri dəyişdirilə bilməz.")
        for item in self.validated_data["permissions"]:
            RolePermission.objects.update_or_create(
                role=role, module=item["module"], defaults={"is_allowed": item["is_allowed"]}
            )
        return role


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


class UserWriteSerializer(serializers.ModelSerializer):
    """İstifadəçilər səhifəsi: yeni işçi/şagird yaratmaq və ya rolunu/statusunu dəyişmək üçün.
    Login mağaza-daxilində unikaldır (məs. rustem.sagird); mağaza kodu view tərəfindən əlavə olunur."""
    password = serializers.CharField(write_only=True, required=False, min_length=6)
    role_id = serializers.PrimaryKeyRelatedField(source="role", queryset=Role.objects.all(),
                                                  write_only=True, required=False, allow_null=True)
    shop = ShopMiniSerializer(read_only=True)
    branch = BranchMiniSerializer(read_only=True)
    role = RoleSerializer(read_only=True)
    initials = serializers.ReadOnlyField()

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "phone",
                  "password", "role", "role_id", "shop", "branch", "status",
                  "initials", "date_joined", "last_seen_at"]
        read_only_fields = ["id", "date_joined", "last_seen_at"]

    def validate_role_id(self, role):
        request = self.context.get("request")
        if request and role.shop_id != request.user.shop_id:
            raise serializers.ValidationError("Bu rol sizin mağazanıza aid deyil.")
        return role

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        request = self.context["request"]
        validated_data["shop"] = request.user.shop
        validated_data["branch"] = request.user.branch
        user = User(**validated_data)
        user.set_password(password or User.objects.make_random_password(10))
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save(update_fields=["password"])
        return user


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