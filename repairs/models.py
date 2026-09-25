import datetime
from django.db import models
from django.utils import timezone
from tenants.models import Shop, Branch
from customers.models import Customer
from accounts.models import User


class RepairStatus(models.TextChoices):
    RECEIVED = "received", "Qəbul edildi"
    DIAGNOSING = "diagnosing", "Diaqnostikada"
    WAITING_REPAIR = "waiting_repair", "Təmir gözləyir"
    IN_PROGRESS = "in_progress", "Təmir prosesində"
    READY = "ready", "Hazırdır"
    DELIVERED = "delivered", "Təhvil verildi"
    CANCELLED = "cancelled", "Ləğv edildi"


class PaymentStatus(models.TextChoices):
    UNPAID = "unpaid", "Ödənilməyib"
    PARTIAL = "partial", "Qismən ödənilib"
    PAID = "paid", "Ödənilib"
    DEBT = "debt", "Borc qalıb"


class RepairOrder(models.Model):
    """Bir 'Yeni xidmət' formunun nəticəsi. Cihaz məlumatı da eyni modeldə saxlanılır (sadəlik üçün)."""

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="repair_orders")
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, related_name="repair_orders")
    number = models.CharField(max_length=32, editable=False, db_index=True)

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="repair_orders")

    # Cihaz
    device_brand = models.CharField(max_length=80)
    device_model = models.CharField(max_length=120)
    device_imei = models.CharField(max_length=64, blank=True)
    device_serial = models.CharField(max_length=64, blank=True)
    accessories_note = models.CharField(max_length=255, blank=True, help_text="Qablaşdırma, adapter və s.")

    # İş
    issue_description = models.TextField()
    work_done_note = models.TextField(blank=True)

    # Maliyyə
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Maya dəyəri")
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Satış qiyməti")

    status = models.CharField(max_length=20, choices=RepairStatus.choices, default=RepairStatus.RECEIVED)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID)
    debt_due_date = models.DateField(null=True, blank=True)

    # Zəmanət — cihaz təhvil veriləndə başlayır
    warranty_days = models.PositiveIntegerField(default=0)
    warranty_started_at = models.DateField(null=True, blank=True)

    received_at = models.DateTimeField(default=timezone.now)
    delivered_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="created_repairs")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["shop", "number"], name="unique_repair_number_per_shop")
        ]

    def save(self, *args, **kwargs):
        if not self.number:
            year = timezone.now().year
            last = (
                RepairOrder.objects.filter(shop=self.shop, number__startswith=f"SRV-{year}-")
                .order_by("-number")
                .first()
            )
            seq = int(last.number.split("-")[-1]) + 1 if last else 1
            self.number = f"SRV-{year}-{seq:06d}"
        super().save(*args, **kwargs)

    @property
    def profit(self):
        return self.sale_price - self.cost_price

    @property
    def paid_amount(self):
        return sum(p.amount for p in self.payments.all())

    @property
    def remaining_debt(self):
        return self.sale_price - self.paid_amount

    @property
    def warranty_end_date(self):
        if self.warranty_started_at and self.warranty_days:
            return self.warranty_started_at + datetime.timedelta(days=self.warranty_days)
        return None

    @property
    def warranty_days_left(self):
        end = self.warranty_end_date
        if not end:
            return None
        return (end - timezone.now().date()).days

    def __str__(self):
        return self.number


class PaymentMethod(models.TextChoices):
    CASH = "cash", "Nağd"
    CARD = "card", "Kart"
    BANK_TRANSFER = "bank_transfer", "Bank köçürməsi"


class RepairPayment(models.Model):
    repair = models.ForeignKey(RepairOrder, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    paid_at = models.DateTimeField(default=timezone.now)
    received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        ordering = ["-paid_at"]

    def __str__(self):
        return f"{self.repair.number} · {self.amount}"
