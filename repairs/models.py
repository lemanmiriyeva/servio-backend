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

    def recompute_payment_status(self, save=True):
        """
        Ödəniş statusunu real vəziyyətə uyğun yeniləyir — bax bölmə 9:
        'Qalan məbləğ avtomatik olaraq müştərinin borclarına əlavə edilə bilər.'
        Bu, tək yerdən idarə olunur ki, Borclar/Hesabatlar/Dashboard-un
        `payment_status='debt'` filtri həmişə düzgün nəticə versin.
        """
        remaining = self.remaining_debt
        if remaining <= 0:
            new_status = PaymentStatus.PAID
        elif self.status == RepairStatus.DELIVERED:
            # Cihaz artıq təhvil verilib, amma tam ödənilməyib — bu, izlənməli borcdur.
            new_status = PaymentStatus.DEBT
        elif self.paid_amount > 0:
            new_status = PaymentStatus.PARTIAL
        else:
            new_status = PaymentStatus.UNPAID
        if new_status != self.payment_status:
            self.payment_status = new_status
            if save:
                self.save(update_fields=["payment_status"])
        return self.payment_status

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


class SupplierReturnStatus(models.TextChoices):
    NOT_SENT = "not_sent", "Təchizatçıya göndərilməyib"
    PENDING = "pending", "Təchizatçıda gözləyir"
    ACCEPTED = "accepted", "Təchizatçı qəbul etdi"
    REJECTED = "rejected", "Təchizatçı rədd etdi"


class RepairWarrantyReturn(models.Model):
    """
    Zəmanət müddətində qaytarılan hissə — məs. dəyişdirilmiş ekran yenidən sınıb.
    Bu qeyd: (1) əvvəlki maya/mənfəəti düzəldir, (2) hissəni təchizatçıya geri
    göndərməyi izləyir, (3) təchizatçının qəbul/rədd qərarına görə anbar və
    maliyyəni yeniləyir.
    """
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="warranty_returns")
    repair = models.ForeignKey(RepairOrder, on_delete=models.CASCADE, related_name="warranty_returns")
    reason = models.TextField(help_text="Müştərinin şikayəti, məs. 'Ekran sensoru yenidən işləmir'")
    refund_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Müştəriyə nağd qaytarılan məbləğ (varsa)",
    )

    supplier_purchase = models.ForeignKey(
        "suppliers.SupplierPurchase", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="warranty_returns",
    )
    return_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Təchizatçıdan geri istənən hissənin dəyəri",
    )
    supplier_status = models.CharField(
        max_length=20, choices=SupplierReturnStatus.choices, default=SupplierReturnStatus.NOT_SENT
    )
    supplier_note = models.CharField(max_length=255, blank=True)
    supplier_resolved_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def send_to_supplier(self):
        if self.supplier_purchase_id and self.supplier_status == SupplierReturnStatus.NOT_SENT:
            self.supplier_status = SupplierReturnStatus.PENDING
            self.save(update_fields=["supplier_status"])

    def resolve_supplier(self, decision: str, note: str = ""):
        """Təchizatçının qərarı: qəbul (borc/maya düzəlişi) və ya rədd (Zay anbarına)."""
        from decimal import Decimal
        if decision not in (SupplierReturnStatus.ACCEPTED, SupplierReturnStatus.REJECTED):
            raise ValueError("decision 'accepted' və ya 'rejected' olmalıdır.")

        self.supplier_note = note
        self.supplier_resolved_at = timezone.now()
        self.supplier_status = decision

        if decision == SupplierReturnStatus.ACCEPTED:
            # Təchizatçı qəbul etdi — bu hissənin maya dəyəri artıq bu təmirin
            # üzərinə yazılmamalıdır: alışı və təmirin maya dəyərini azaldırıq.
            if self.supplier_purchase_id:
                sp = self.supplier_purchase
                sp.amount = max(sp.amount - self.return_amount, Decimal("0"))
                sp.save(update_fields=["amount"])
            self.repair.cost_price = max(self.repair.cost_price - self.return_amount, Decimal("0"))
            self.repair.save(update_fields=["cost_price"])
        else:
            # Təchizatçı rədd etdi (məs. fiziki zədə, ləkə) — hissə Zay anbarına düşür,
            # maya dəyəri təmirin üzərində qalır (dükan itkini öz üzərinə götürür).
            from inventory.models import Product, StockMovement, MovementType
            part_name = (self.supplier_purchase.description if self.supplier_purchase_id else self.reason)[:120]
            product, created = Product.objects.get_or_create(
                shop=self.shop, name=f"ZAY — {part_name}",
                defaults={"category": "Zay / Qaytarılmış", "unit_cost": self.return_amount, "is_scrap": True},
            )
            if not product.is_scrap:
                product.is_scrap = True
                product.save(update_fields=["is_scrap"])
            StockMovement.objects.create(
                shop=self.shop, product=product, movement_type=MovementType.WARRANTY_REJECTED_IN,
                quantity_delta=1, related_repair=self.repair,
                note=f"{self.repair.number} — zəmanət qaytarması, təchizatçı qəbul etmədi ({note})".strip(),
            )
        self.save()

    def __str__(self):
        return f"{self.repair.number} — zəmanət qaytarması"