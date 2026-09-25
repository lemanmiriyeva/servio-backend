from django.contrib import admin
from .models import Supplier, SupplierPurchase


class SupplierPurchaseInline(admin.TabularInline):
    model = SupplierPurchase
    extra = 0


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "shop", "phone")
    list_filter = ("shop",)
    inlines = [SupplierPurchaseInline]
