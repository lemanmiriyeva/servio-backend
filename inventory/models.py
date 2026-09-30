from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from tenants.models import Shop
from accounts.models import User
from repairs.models import RepairOrder


class Product(models.Model):
    """Anbardakı bir ehtiyat hissəsi / məhsul (mağazaya aiddir)."""
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="products")
    name = models.CharField(max_length=150)
    brand = models.CharField(max_length=80, blank=True)
    category = models.CharField(max_length=80, blank=True, help_text="Ekran, Batareya, Anakart və s.")
    sku = models.CharField(max_length=60, blank=True, help_text="Daxili kod")

    quantity_in_stock = models.PositiveIntegerField(default=0)
    min_stock_alert = models.PositiveIntegerField(default=2, help_text="Bu miqdardan aşağı düşəndə xəbərdarlıq")

    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Maya dəyəri")
    unit_sale_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Öz servisin satış qiyməti")

    # --- Marketplace (mağazalararası bazar) ---
    is_shared_to_marketplace = models.BooleanField(
        default=False,
        help_text="Aktiv olarsa, digər mağazaların ustaları bu məhsulu axtarışda görüb sifariş göndərə bilər",
    )
    marketplace_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Digər mağazalara satış qiyməti (boşdursa unit_sale_price istifadə olunur)",
    )

    is_scrap = models.BooleanField(
        default=False,
        help_text="Zəmanət altında qaytarılıb, təchizatçı qəbul etməyib — satışa çıxarılmır (Zay anbarı)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["shop", "name"])]
        constraints = [
            # `sku__gt=""` semantik olaraq `~Q(sku="")` (boş olmayan SKU) ilə eynidir,
            # amma mssql-django-nun mənfi (NOT) şərtləri filtrlənmiş indeksə çevirərkən
            # yanlış SQL sintaksisi yaratması problemini keçir.
            models.UniqueConstraint(fields=["shop", "sku"], name="unique_sku_per_shop",
                                     condition=models.Q(sku__gt=""))
        ]

    @property
    def is_low_stock(self) -> bool:
        return self.quantity_in_stock <= self.min_stock_alert

    @property
    def effective_marketplace_price(self):
        return self.marketplace_price or self.unit_sale_price

    def __str__(self):
        return f"{self.name} ({self.shop.name})"


class MovementType(models.TextChoices):
    PURCHASE_IN = "purchase_in", "Alış (daxil olma)"
    REPAIR_USE = "repair_use", "Təmirdə istifadə (sərfiyyat)"
    ADJUSTMENT = "adjustment", "Əl ilə düzəliş"
    MARKETPLACE_OUT = "marketplace_out", "Başqa mağazaya satış"
    MARKETPLACE_IN = "marketplace_in", "Başqa mağazadan alış"
    WARRANTY_REJECTED_IN = "warranty_rejected_in", "Zəmanət qaytarması (təchizatçı qəbul etmədi)"


class StockMovement(models.Model):
    """Anbar hərəkəti — hər dəyişiklik qeydə alınır, quantity_in_stock bundan hesablanır."""
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="stock_movements")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="movements")
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    quantity_delta = models.IntegerField(help_text="Müsbət: daxil olma, Mənfi: çıxış")
    note = models.CharField(max_length=255, blank=True)
    related_repair = models.ForeignKey(RepairOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name="stock_movements")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if not self.pk:
                new_qty = self.product.quantity_in_stock + self.quantity_delta
                if new_qty < 0:
                    raise ValidationError("Anbarda kifayət qədər məhsul yoxdur.")
                self.product.quantity_in_stock = new_qty
                self.product.save(update_fields=["quantity_in_stock", "updated_at"])
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product} · {self.quantity_delta:+d}"


class RepairPartUsage(models.Model):
    """Bir təmirdə istifadə olunan ehtiyat hissəsi — anbardan avtomatik düşür."""
    repair = models.ForeignKey(RepairOrder, on_delete=models.CASCADE, related_name="parts_used")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="repair_usages")
    quantity = models.PositiveIntegerField(default=1)
    unit_cost_at_use = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        if is_new and not self.unit_cost_at_use:
            self.unit_cost_at_use = self.product.unit_cost
        super().save(*args, **kwargs)
        if is_new:
            StockMovement.objects.create(
                shop=self.product.shop,
                product=self.product,
                movement_type=MovementType.REPAIR_USE,
                quantity_delta=-self.quantity,
                related_repair=self.repair,
                note=f"{self.repair.number} üçün sərf edildi",
            )

    def __str__(self):
        return f"{self.repair.number} · {self.product.name} x{self.quantity}"