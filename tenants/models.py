import uuid
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Plan(models.Model):
    """Abunəlik planı (Basic, Pro və s.) — həm daxili abunə, həm də ictimai Qiymətlər
    səhifəsi üçün istifadə olunur (public_* sahələri marketinq göstərimi üçündür)."""
    name = models.CharField(max_length=50, unique=True)
    price_monthly = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_yearly = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="İllik ödəniş seçimi (AZN). Boş saxlansa, Qiymətlər səhifəsində illik seçim göstərilmir.",
    )
    max_branches = models.PositiveIntegerField(default=1)
    max_users = models.PositiveIntegerField(default=3)

    # --- İctimai "Qiymətlər" səhifəsi üçün (Baş Admin idarə edir) ---
    public_description = models.CharField(max_length=200, blank=True,
                                            help_text="Qiymətlər səhifəsində planın altındakı qısa izah")
    public_description_yearly = models.CharField(
        max_length=200, blank=True,
        help_text="İllik ödəniş seçimi göstəriləndə onun altında görünən qısa izah (məs. '2 ay pulsuz').",
    )
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

    is_active = models.BooleanField(
        default=True,
        help_text="Söndürülübsə, bu mağazanın HEÇ BİR istifadəçisi giriş edə bilmir.",
    )
    disabled_reason = models.CharField(
        max_length=255, blank=True,
        help_text="Mağaza bağlıdırsa səbəb — avtomatik (ödəniş vaxtı keçib) və ya Baş Admin "
                   "tərəfindən əl ilə yazılıb. Giriş zamanı istifadəçiyə bu mətn göstərilir.",
    )
    disabled_at = models.DateTimeField(null=True, blank=True)
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

    # ------------------------------------------------------------ abunə/ödəniş
    @property
    def days_to_payment(self):
        """Növbəti ödənişə qalan gün sayı (mənfi = artıq gecikib). next_payment_at yoxdursa None."""
        if not self.next_payment_at:
            return None
        return (self.next_payment_at - timezone.now().date()).days

    @property
    def payment_urgency(self):
        """Frontend-də rəng kodlaşdırması üçün: ok (yaşıl) / warning (sarı, <=7g) /
        soon (narıncı, <=3g) / critical (qırmızı, <=1g və ya artıq keçib)."""
        days = self.days_to_payment
        if days is None:
            return "ok"
        if days <= 1:
            return "critical"
        if days <= 3:
            return "soon"
        if days <= 7:
            return "warning"
        return "ok"

    def check_and_auto_disable(self):
        """Ödəniş tarixi keçib və mağaza hələ aktivdirsə, avtomatik bağlayır.
        Vəziyyət dəyişdirilibsə True qaytarır. Giriş zamanı (LoginView) çağırılır."""
        if self.is_active and self.next_payment_at and self.next_payment_at < timezone.now().date():
            self.is_active = False
            self.status = self.Status.BLOCKED
            self.disabled_reason = (
                f"Planın ödəniş tarixi ({self.next_payment_at.strftime('%d.%m.%Y')}) keçib, "
                f"ödəniş qeydə alınmayıb."
            )
            self.disabled_at = timezone.now()
            self.save(update_fields=["is_active", "status", "disabled_reason", "disabled_at"])
            return True
        return False

    def reactivate(self, *, months=1):
        """Ödəniş qeydə alınanda (SubscriptionPayment yaradılanda) çağırılır: mağazanı
        aktivləşdirir, səbəbi təmizləyir, növbəti ödəniş tarixini irəli aparır."""
        base = self.next_payment_at if (self.next_payment_at and self.next_payment_at >= timezone.now().date()) \
            else timezone.now().date()
        self.next_payment_at = base + timezone.timedelta(days=30 * months)
        self.is_active = True
        self.status = self.Status.ACTIVE
        self.disabled_reason = ""
        self.disabled_at = None
        self.save(update_fields=["next_payment_at", "is_active", "status", "disabled_reason", "disabled_at"])


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