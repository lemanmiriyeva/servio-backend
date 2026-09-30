import uuid
from django.db import models
from django.utils.text import slugify


class Plan(models.Model):
    """Abunəlik planı (Basic, Pro və s.) — həm daxili abunə, həm də ictimai Qiymətlər
    səhifəsi üçün istifadə olunur (public_* sahələri marketinq göstərimi üçündür)."""
    name = models.CharField(max_length=50, unique=True)
    price_monthly = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_branches = models.PositiveIntegerField(default=1)
    max_users = models.PositiveIntegerField(default=3)

    # --- İctimai "Qiymətlər" səhifəsi üçün (Baş Admin idarə edir) ---
    public_description = models.CharField(max_length=200, blank=True,
                                            help_text="Qiymətlər səhifəsində planın altındakı qısa izah")
    public_features = models.TextField(blank=True, help_text="Hər sətirdə bir üstünlük")
    is_featured = models.BooleanField(default=False, help_text="\"Ən populyar\" kimi vurğulanır")
    show_on_pricing_page = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "price_monthly"]

    def public_features_list(self):
        return [f.strip() for f in self.public_features.splitlines() if f.strip()]

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

    # Qəbzdə/mağaza profilində göstərilən məlumatlar (bölmə 2 və 15)
    address = models.CharField(max_length=255, blank=True, help_text="Qəbzdə görünəcək ünvan")
    phone = models.CharField(max_length=32, blank=True, help_text="Qəbzdə görünəcək telefon")
    work_hours = models.CharField(max_length=120, blank=True, help_text="Məs: B.e – Şənbə 10:00–19:00")
    tax_id = models.CharField(max_length=32, blank=True, help_text="VÖEN (istəyə bağlı)")
    receipt_terms = models.TextField(
        blank=True,
        default=(
            "1. Zəmanət yalnız görülən işə və dəyişdirilən detala şamil olur, "
            "cihazın digər hissələrinə aid deyil.\n"
            "2. Fiziki zədə, maye təması və üçüncü şəxs müdaxiləsi zəmanəti ləğv edir.\n"
            "3. Təmir bitdikdən sonra cihaz 30 gün ərzində götürülməlidir, bu müddətdən "
            "sonra servis saxlama üçün məsuliyyət daşımır.\n"
            "4. Cihaz yalnız bu sənəd və şəxsiyyət vəsiqəsi təqdim edildikdə təhvil verilir."
        ),
        help_text="Qəbzin altında görünəcək zəmanət/təhvil-təslim şərtləri",
    )

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
            base = slugify(self.name)[:54] or "shop"
            code, i = base, 2
            while Shop.objects.filter(code=code).exclude(pk=self.pk).exists():
                code = f"{base}-{i}"
                i += 1
            self.code = code
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