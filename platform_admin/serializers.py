from rest_framework import serializers
from .models import SupportTicket, SubscriptionPayment, ContactInquiry


class ContactInquiryPublicSerializer(serializers.ModelSerializer):
    """İctimai '/elaqe' formu üçün — AllowAny, yalnız yaratmaq olar."""

    class Meta:
        model = ContactInquiry
        fields = ["full_name", "phone", "message"]


class SupportTicketSerializer(serializers.ModelSerializer):
    shop_name = serializers.CharField(source="shop.name", read_only=True)

    class Meta:
        model = SupportTicket
        fields = ["id", "shop", "shop_name", "subject", "message", "status", "created_at"]
        read_only_fields = ["id", "created_at"]


class SubscriptionPaymentSerializer(serializers.ModelSerializer):
    shop_name = serializers.CharField(source="shop.name", read_only=True)

    class Meta:
        model = SubscriptionPayment
        fields = ["id", "shop", "shop_name", "amount", "paid_at", "period_start", "period_end"]