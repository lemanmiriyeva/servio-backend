from rest_framework import serializers
from inventory.models import Product
from .models import MarketplaceOrder


class MarketplaceProductSearchSerializer(serializers.ModelSerializer):
    """
    DİQQƏT: bu, başqa mağazalara göstərilən nümunədir.
    unit_cost (maya dəyəri) BURADA YOXDUR — qəsdən.
    """
    shop_id = serializers.CharField(source="shop.id", read_only=True)
    shop_name = serializers.CharField(source="shop.name", read_only=True)
    shop_city = serializers.CharField(source="shop.city", read_only=True)
    price = serializers.DecimalField(source="effective_marketplace_price", max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Product
        fields = ["id", "name", "brand", "category", "quantity_in_stock",
                  "price", "shop_id", "shop_name", "shop_city"]


class MarketplaceOrderSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    buyer_shop_name = serializers.CharField(source="buyer_shop.name", read_only=True)
    seller_shop_name = serializers.CharField(source="seller_shop.name", read_only=True)
    total_price = serializers.ReadOnlyField()

    class Meta:
        model = MarketplaceOrder
        fields = [
            "id", "buyer_shop", "buyer_shop_name", "seller_shop", "seller_shop_name",
            "product", "product_name", "quantity", "unit_price", "total_price",
            "payment_method", "status", "buyer_note", "seller_note",
            "related_repair", "created_at", "responded_at", "paid_at", "completed_at",
        ]
        read_only_fields = [
            "id", "seller_shop", "unit_price", "status", "seller_note",
            "created_at", "responded_at", "paid_at", "completed_at",
        ]

    def create(self, validated_data):
        request = self.context["request"]
        product = validated_data["product"]
        if not product.is_shared_to_marketplace:
            raise serializers.ValidationError("Bu məhsul marketplace-ə açıq deyil.")
        validated_data["buyer_shop"] = request.user.shop
        validated_data["buyer_branch"] = request.user.branch
        validated_data["requested_by"] = request.user
        validated_data["seller_shop"] = product.shop
        validated_data["unit_price"] = product.effective_marketplace_price
        return super().create(validated_data)
