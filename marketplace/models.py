"""
Mağazalararası bazar (Marketplace).

Ssenari: Bir mağazanın ustası təmir üçün lazım olan hissəni öz anbarında tapmır.
Platformada digər mağazaların "paylaşıma açıq" (is_shared_to_marketplace=True) elan etdiyi
məhsulları axtarır, sifariş göndərir. Satıcı mağaza qəbul edir, ödəniş qeydə alınır,
göndərilir və tamamlanır — bütün addımlar StockMovement və CashTransaction ilə izlənir.

DİQQƏT — tenant-təcrid istisnası: bu modul QƏSDƏN iki fərqli mağazanı bir-birinə bağlayır.
API qatında axtarış yalnız is_shared_to_marketplace=True olan məhsulları, yalnız
ad/marka/kateqoriya/qiymət/miqdar sahələrini göstərməlidir — maya dəyəri (unit_cost) HEÇ VAXT
başqa mağazaya göstərilmir.
"""
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from tenants.models import Shop, Branch
from accounts.models import User
from inventory.models import Product, StockMovement, MovementType
from finance.models import CashTransaction, TransactionType, PaymentMethod
from repairs.models import RepairOrder


class OrderStatus(models.TextChoices):
    PENDING = "pending", "Gözləyir"
    ACCEPTED = "accepted", "Qəbul edildi"
    REJECTED = "rejected", "Rədd edildi"
    PAID = "paid", "Ödənilib"
    SHIPPED = "shipped", "Göndərilib"
    COMPLETED = "completed", "Tamamlandı"
    CANCELLED = "cancelled", "Ləğv edildi"


class MarketplaceOrder(models.Model):
    # Alıcı tərəf
    buyer_shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="marketplace_purchases")
    buyer_branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="marketplace_requests")
    related_repair = models.ForeignKey(RepairOrder, on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name="marketplace_orders",
                                        help_text="Hansı təmir üçün lazımdır (opsional)")

    # Satıcı tərəf
    seller_shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="marketplace_sales")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="marketplace_orders")

    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Sifariş anındakı qiymət (snapshot)")
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.BANK_TRANSFER)

    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING)
    buyer_note = models.CharField(max_length=255, blank=True)
    seller_note = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    responded_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=~models.Q(buyer_shop=models.F("seller_shop")),
                                    name="marketplace_buyer_seller_differ"),
        ]

    @property
    def total_price(self):
        return self.unit_price * self.quantity

    # --- Status keçidləri (biznes qaydaları burada, view-lar sadəcə çağırır) ---

    def accept(self):
        if self.status != OrderStatus.PENDING:
            raise ValidationError("Yalnız gözləyən sifariş qəbul edilə bilər.")
        with transaction.atomic():
            if self.product.quantity_in_stock < self.quantity:
                raise ValidationError("Satıcının anbarında kifayət qədər məhsul yoxdur.")
            StockMovement.objects.create(
                shop=self.seller_shop, product=self.product,
                movement_type=MovementType.MARKETPLACE_OUT,
                quantity_delta=-self.quantity,
                note=f"Marketplace sifariş #{self.pk} → {self.buyer_shop.name}",
            )
            self.status = OrderStatus.ACCEPTED
            self.responded_at = timezone.now()
            self.save(update_fields=["status", "responded_at"])

    def reject(self, note: str = ""):
        if self.status != OrderStatus.PENDING:
            raise ValidationError("Yalnız gözləyən sifariş rədd edilə bilər.")
        self.status = OrderStatus.REJECTED
        self.seller_note = note
        self.responded_at = timezone.now()
        self.save(update_fields=["status", "seller_note", "responded_at"])

    def cancel(self):
        if self.status not in (OrderStatus.PENDING, OrderStatus.ACCEPTED):
            raise ValidationError("Bu mərhələdə sifariş ləğv edilə bilməz.")
        with transaction.atomic():
            if self.status == OrderStatus.ACCEPTED:
                # ehtiyat hissəsini satıcının anbarına geri qaytar
                StockMovement.objects.create(
                    shop=self.seller_shop, product=self.product,
                    movement_type=MovementType.ADJUSTMENT,
                    quantity_delta=self.quantity,
                    note=f"Marketplace sifariş #{self.pk} ləğv edildi — geri qaytarıldı",
                )
            self.status = OrderStatus.CANCELLED
            self.save(update_fields=["status"])

    def mark_paid(self):
        if self.status != OrderStatus.ACCEPTED:
            raise ValidationError("Yalnız qəbul edilmiş sifariş üçün ödəniş qeydə alına bilər.")
        with transaction.atomic():
            CashTransaction.objects.create(
                shop=self.seller_shop, type=TransactionType.INCOME,
                amount=self.total_price, method=self.payment_method,
                description=f"Marketplace satış — {self.product.name} x{self.quantity} ({self.buyer_shop.name})",
            )
            self.status = OrderStatus.PAID
            self.paid_at = timezone.now()
            self.save(update_fields=["status", "paid_at"])

    def mark_shipped(self):
        if self.status != OrderStatus.PAID:
            raise ValidationError("Yalnız ödənilmiş sifariş göndərilə bilər.")
        self.status = OrderStatus.SHIPPED
        self.save(update_fields=["status"])

    def mark_completed(self):
        """Alıcı mağaza məhsulu aldığını təsdiqləyir — öz anbarına əlavə olunur."""
        if self.status != OrderStatus.SHIPPED:
            raise ValidationError("Yalnız göndərilmiş sifariş tamamlanmış sayıla bilər.")
        with transaction.atomic():
            buyer_product, _ = Product.objects.get_or_create(
                shop=self.buyer_shop, sku=f"MP-{self.product_id}",
                defaults=dict(
                    name=self.product.name, brand=self.product.brand,
                    category=self.product.category, unit_cost=self.unit_price,
                ),
            )
            StockMovement.objects.create(
                shop=self.buyer_shop, product=buyer_product,
                movement_type=MovementType.MARKETPLACE_IN,
                quantity_delta=self.quantity,
                note=f"Marketplace sifariş #{self.pk} — {self.seller_shop.name}-dan",
            )
            self.status = OrderStatus.COMPLETED
            self.completed_at = timezone.now()
            self.save(update_fields=["status", "completed_at"])

    def __str__(self):
        return f"{self.buyer_shop.name} ← {self.seller_shop.name} · {self.product.name} x{self.quantity}"
