from rest_framework import serializers
from .models import Product, StockMovement


class ProductSerializer(serializers.ModelSerializer):
    is_low_stock = serializers.ReadOnlyField()

    class Meta:
        model = Product
        fields = [
            "id", "name", "brand", "category", "sku",
            "quantity_in_stock", "min_stock_alert", "is_low_stock",
            "unit_cost", "unit_sale_price",
            "is_shared_to_marketplace", "marketplace_price",
            "created_at",
        ]
        read_only_fields = ["id", "quantity_in_stock", "created_at"]


class StockMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = StockMovement
        fields = ["id", "product", "product_name", "movement_type", "quantity_delta",
                  "note", "related_repair", "created_at"]
        read_only_fields = ["id", "created_at"]

    def create(self, validated_data):
        request = self.context["request"]
        validated_data["shop"] = request.user.shop
        validated_data["created_by"] = request.user
        return super().create(validated_data)
