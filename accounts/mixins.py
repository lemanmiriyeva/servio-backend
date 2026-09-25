"""
Bütün mağaza-daxili (tenant) API view-ları bu mixin-dən istifadə etməlidir.
Bu, dizaynda qeyd olunan tələbi tətbiq edir:
"server tərəfində hər sorğu mağaza ID-si ilə filtrlənməlidir ki, bir mağazanın işçisi
başqasının məlumatına heç bir halda çıxış əldə edə bilməsin."
"""
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission


class ShopScopedQuerysetMixin:
    """ViewSet/generic view üçün: get_queryset() avtomatik olaraq request.user.shop ilə filtrlənir."""
    shop_field = "shop"

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_platform_admin or user.is_superuser:
            return qs
        if not user.shop_id:
            return qs.none()
        return qs.filter(**{self.shop_field: user.shop_id})

    def perform_create(self, serializer):
        user = self.request.user
        save_kwargs = {}
        if self.shop_field not in serializer.validated_data and not (user.is_platform_admin or user.is_superuser):
            save_kwargs[self.shop_field] = user.shop
        serializer.save(**save_kwargs)


class HasModulePermission(BasePermission):
    """
    ViewSet-ə `module_code = accounts.models.Module.XXX` təyin edin.
    Sahib (is_owner_role) və Platform Admin həmişə keçir.
    """
    def has_permission(self, request, view):
        module_code = getattr(view, "module_code", None)
        if module_code is None:
            return True
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_platform_admin or user.is_superuser:
            return True
        return user.has_module_permission(module_code)


class IsPlatformAdmin(BasePermission):
    """Yalnız Platform Super Admin (`is_platform_admin=True` və ya Django superuser)."""
    message = "Bu bölmə yalnız platforma admini üçündür."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_platform_admin or user.is_superuser))


class ShopOwnQuerysetMixin:
    """
    Bir mağazanın öz Shop qeydini (settings) əldə etməsi üçün — filtr `pk` ilə deyil,
    həmişə `request.user.shop` ilə edilir ki, başqa mağazanı heç vaxt görə/redaktə edə bilməsin.
    """
    def get_object(self):
        return self.request.user.shop


def require_module(user, module_code: str):
    if not user.has_module_permission(module_code):
        raise PermissionDenied("Bu bölməyə giriş icazəniz yoxdur.")
