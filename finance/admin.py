from django.contrib import admin
from .models import CashTransaction, CashboxOpeningBalance


@admin.register(CashTransaction)
class CashTransactionAdmin(admin.ModelAdmin):
    list_display = ("shop", "type", "amount", "method", "description", "created_at")
    list_filter = ("shop", "type", "method")
    search_fields = ("description",)


@admin.register(CashboxOpeningBalance)
class CashboxOpeningBalanceAdmin(admin.ModelAdmin):
    list_display = ("shop", "branch", "amount", "as_of_date")
