from django.contrib import admin
from .models import Plan, Shop, Branch


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "price_monthly", "price_yearly", "max_branches", "max_users")
    search_fields = ("name",)


class BranchInline(admin.TabularInline):
    model = Branch
    extra = 0


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "status", "plan", "city", "created_at")
    list_filter = ("status", "plan")
    search_fields = ("name", "code", "owner_full_name", "owner_phone")
    readonly_fields = ("created_at",)
    inlines = [BranchInline]


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "shop", "is_main", "phone")
    list_filter = ("shop",)