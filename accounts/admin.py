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
    inlines = [RolePermissionInline]


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "get_full_name", "shop", "role", "status", "is_platform_admin")
    list_filter = ("shop", "role", "status", "is_platform_admin")
    fieldsets = BaseUserAdmin.fieldsets + (
        ("ServisCRM", {"fields": ("shop", "branch", "role", "phone", "is_platform_admin", "status")}),
    )
