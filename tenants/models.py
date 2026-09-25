import uuid
from django.db import models
from django.utils.text import slugify


class Plan(models.Model):
    """Abunəlik planı (Basic, Pro və s.)"""
    name = models.CharField(max_length=50, unique=True)
    price_monthly = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_branches = models.PositiveIntegerField(default=1)
    max_users = models.PositiveIntegerField(default=3)

    def __str__(self):
        return self.name


class Shop(models.Model):
    """Bir servis mərkəzi = bir tenant. Bütün digər məlumatlar buna bağlıdır."""

    class Status(models.TextChoices):
        TRIAL = "trial", "Sınaq müddətində"
        ACTIVE = "active", "Aktiv"
        OVERDUE = "overdue", "Ödəniş gecikib"
        BLOCKED = "blocked", "Bloklanıb"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150)
    code = models.SlugField(max_length=60, unique=True, help_text="Giriş üçün: istifadeci.KOD")
    owner_full_name = models.CharField(max_length=150, blank=True)
    owner_phone = models.CharField(max_length=32, blank=True)
    owner_email = models.EmailField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    logo_initials = models.CharField(max_length=4, blank=True)

    plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True, blank=True, related_name="shops")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TRIAL)
    trial_ends_at = models.DateField(null=True, blank=True)
    next_payment_at = models.DateField(null=True, blank=True)

    # Zəmanət/servis defolt parametrləri (Parametrlər səhifəsi üçün)
    default_warranty_days = models.PositiveIntegerField(default=14)
    currency = models.CharField(max_length=8, default="AZN")

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = slugify(self.name)[:60]
        if not self.logo_initials:
            parts = self.name.split()
            self.logo_initials = "".join(p[0] for p in parts[:2]).upper()
        super().save(*args, **kwargs)


class Branch(models.Model):
    """Mağazanın filialı."""
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="branches")
    name = models.CharField(max_length=150)
    address = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    is_main = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_main", "name"]
        constraints = [
            models.UniqueConstraint(fields=["shop", "name"], name="unique_branch_name_per_shop")
        ]

    def __str__(self):
        return f"{self.shop.name} — {self.name}"
