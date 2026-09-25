from django.contrib import admin
from .models import RepairOrder, RepairPayment


class RepairPaymentInline(admin.TabularInline):
    model = RepairPayment
    extra = 0


@admin.register(RepairOrder)
class RepairOrderAdmin(admin.ModelAdmin):
    list_display = ("number", "shop", "customer", "device_model", "status", "payment_status", "sale_price")
    list_filter = ("shop", "status", "payment_status")
    search_fields = ("number", "customer__full_name", "device_imei", "device_serial")
    inlines = [RepairPaymentInline]
