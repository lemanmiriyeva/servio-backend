from django.contrib import admin
from .models import MarketplaceOrder


@admin.register(MarketplaceOrder)
class MarketplaceOrderAdmin(admin.ModelAdmin):
    list_display = ("id", "buyer_shop", "seller_shop", "product", "quantity", "unit_price", "status", "created_at")
    list_filter = ("status", "buyer_shop", "seller_shop")
