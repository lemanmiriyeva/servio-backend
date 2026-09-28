from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, Role, RolePermission


class RolePermissionInline(admin.TabularInline):
    model = RolePermission
    extra = 0


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "shop", "is_owner_role")
    list_filter = ("shop", "is_owner_role")
    search_fields = ("name", "shop__name")
    inlines = [RolePermissionInline]


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "get_full_name", "shop", "role", "status", "is_platform_admin", "is_active")
    list_filter = ("shop", "role", "status", "is_platform_admin", "is_active")
    search_fields = ("username", "first_name", "last_name", "email", "phone", "shop__name")
    list_select_related = ("shop", "role")
    autocomplete_fields = ("shop",)
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Servio", {"fields": ("shop", "branch", "role", "phone", "is_platform_admin", "status", "last_seen_at")}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("Servio", {"fields": ("shop", "branch", "role", "phone", "is_platform_admin", "status")}),
    )
