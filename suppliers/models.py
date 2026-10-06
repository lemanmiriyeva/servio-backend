from django.db import models
from django.utils import timezone
from tenants.models import Shop


class PurchaseStatus(models.TextChoices):
    ACTIVE = "active", "Aktiv"
    # Alış bağlı olduğu təmir ləğv ediləndə avtomatik bura keçir — silinmir (tarixçə qalır),
    # amma ümumi təchizatçı borcundan (total_debt) çıxarılır.
    CANCELLED = "cancelled", "Ləğv edildi"


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
        # Ləğv edilmiş alışlar (bağlı təmir ləğv edilib) ümumi məbləğə daxil edilmir.
        return sum(p.amount for p in self.purchases.exclude(status=PurchaseStatus.CANCELLED))

    @property
    def total_paid(self):
        return sum(p.paid_amount for p in self.purchases.exclude(status=PurchaseStatus.CANCELLED))

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
    status = models.CharField(max_length=20, choices=PurchaseStatus.choices, default=PurchaseStatus.ACTIVE)
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


class SupplierPurchasePayment(models.Model):
    """Bir ödənişin (kassadan çıxan məbləğin) konkret bu alışa neçə AZN tətbiq olunduğunun qeydi.
    Bir təchizatçı ödənişi FIFO ilə bir neçə alışa bölünə bilər (bax: SupplierViewSet.pay) —
    buna görə hər alışın öz tarixçəsi (hansı tarixdə nə qədər ödənilib) ayrıca saxlanır,
    ümumi "ödəniş tarixçəsi" siyahısından fərqli olaraq, təchizatçı səhifəsində hər alışın
    ALTINDA konkret o alışa aid ödənişlər göstərilə bilsin deyə."""
    purchase = models.ForeignKey(SupplierPurchase, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_at = models.DateTimeField(default=timezone.now)
    method = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["-paid_at"]

    def __str__(self):
        return f"{self.purchase} · {self.amount}"


def sync_repair_cost_price(repair):
    """
    Bir təmirə bağlı təchizatçı alışı əlavə/redaktə/ləğv olunanda, həmin təmirin "maya dəyəri"
    (cost_price) bağlı (ləğv edilməmiş) alışların cəminə görə yenilənir — əks halda alışı
    dəyişəndə müştərinin mənfəəti köhnə rəqəmlə hesablanmağa davam edirdi.
    Təmirin heç bir (aktiv) alışı yoxdursa toxunmuruq (cost_price əl ilə, birbaşa təmir
    səhifəsindən də yazıla bilər — orda girilən qiyməti burdan sıfırlamamalıyıq).
    """
    from decimal import Decimal

    if repair is None:
        return
    purchases = repair.supplier_purchases.exclude(status=PurchaseStatus.CANCELLED)
    if not purchases.exists():
        return
    total = sum((p.amount for p in purchases), Decimal("0"))
    if repair.cost_price != total:
        repair.cost_price = total
        repair.save(update_fields=["cost_price"])