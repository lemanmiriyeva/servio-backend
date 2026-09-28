from django.db import models
from django.utils import timezone
from tenants.models import Shop


class Supplier(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="suppliers")
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=32, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    @property
    def total_purchased(self):
        return sum(p.amount for p in self.purchases.all())

    @property
    def total_paid(self):
        return sum(p.paid_amount for p in self.purchases.all())

    @property
    def total_debt(self):
        return self.total_purchased - self.total_paid

    def __str__(self):
        return self.name


class SupplierPurchase(models.Model):
    """Təchizatçıdan alınan mal/ehtiyat hissəsi — alış qeydi + qismən ödəniş izlənir."""
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="supplier_purchases")
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name="purchases")
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    purchased_at = models.DateField(default=timezone.now)
    # Könüllü: alış hansı təmir üçün edilib (məs. Leman xanımın iPhone ekranı → iDoctor)
    repair = models.ForeignKey(
        "repairs.RepairOrder", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="supplier_purchases",
    )

    class Meta:
        ordering = ["-purchased_at"]

    @property
    def remaining(self):
        return self.amount - self.paid_amount

    def __str__(self):
        return f"{self.supplier.name} · {self.description}"