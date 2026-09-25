from django.contrib import admin
from .models import SupportTicket, SubscriptionPayment


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ("subject", "shop", "status", "created_at")
    list_filter = ("status",)


@admin.register(SubscriptionPayment)
class SubscriptionPaymentAdmin(admin.ModelAdmin):
    list_display = ("shop", "amount", "period_start", "period_end", "paid_at")
