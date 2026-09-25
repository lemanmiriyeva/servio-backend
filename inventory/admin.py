from django.contrib import admin
from .models import Product, StockMovement, RepairPartUsage


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "shop", "quantity_in_stock", "unit_cost", "unit_sale_price",
                     "is_shared_to_marketplace", "is_low_stock")
    list_filter = ("shop", "is_shared_to_marketplace", "category")
    search_fields = ("name", "sku", "brand")


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("product", "movement_type", "quantity_delta", "created_at")
    list_filter = ("shop", "movement_type")


@admin.register(RepairPartUsage)
class RepairPartUsageAdmin(admin.ModelAdmin):
    list_display = ("repair", "product", "quantity", "unit_cost_at_use")
