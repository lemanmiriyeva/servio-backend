from django.db import models
from django.utils import timezone
from tenants.models import Shop, Branch
from accounts.models import User
from repairs.models import RepairOrder, PaymentMethod
from suppliers.models import Supplier


class TransactionType(models.TextChoices):
    INCOME = "income", "Gəlir"
    EXPENSE = "expense", "Xərc"
    SUPPLIER_PAYMENT = "supplier_payment", "Təchizatçı ödənişi"
    REFUND = "refund", "Geri qaytarma (zəmanət)"


class CashTransaction(models.Model):
    """Kassa səhifəsindəki hər sətir: gəlir, xərc və ya təchizatçıya ödəniş."""
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="cash_transactions")
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, related_name="cash_transactions")

    type = models.CharField(max_length=20, choices=TransactionType.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    description = models.CharField(max_length=255)

    repair = models.ForeignKey(RepairOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name="cash_entries")
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="cash_entries")
    expense_category = models.CharField(max_length=80, blank=True, help_text="Elektrik, İcarə, Maaş və s.")

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["shop", "type", "created_at"])]

    @property
    def signed_amount(self):
        return self.amount if self.type == TransactionType.INCOME else -self.amount

    def __str__(self):
        return f"{self.get_type_display()} · {self.amount}"


class CashboxOpeningBalance(models.Model):
    """Filialın başlanğıc kassa balansı (ay/dövr üçün)."""
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="opening_balances")
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="opening_balances")
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    as_of_date = models.DateField(default=timezone.now)

    class Meta:
        ordering = ["-as_of_date"]
