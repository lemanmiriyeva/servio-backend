"""
İctimai sayt (marketing) səhifələrinin məzmunu: Ana səhifə, Funksiyalar, Qiymətlər,
Haqqımızda, FAQ, Əlaqə — hamısı bura köçürülür ki, Baş Admin (Platform Super Admin)
kod dəyişmədən redaktə edə bilsin. Qiymətlər səhifəsi isə ayrıca model yaratmaq əvəzinə
artıq mövcud olan `tenants.Plan` modelindən (bax: Plan.public_* sahələri) istifadə edir,
çünki bu, həm abunə planı, həm də marketinq qiyməti üçün eyni məlumatdır.

Bütün modellər `platform_admin/resources.py`-dəki generik CRUD-a qeydiyyatdan keçib —
frontend forması avtomatik yaranır, əlavə admin UI kodu lazım deyil.
"""
from django.db import models

ICON_CHOICES = [
    ("Users", "İstifadəçilər"), ("Wrench", "Alət"), ("Boxes", "Qutular"),
    ("Truck", "Yük maşını"), ("Wallet", "Cüzdan"), ("BarChart3", "Qrafik"),
    ("ShieldCheck", "Qalxan"), ("Printer", "Printer"), ("Gauge", "Sürətölçən"),
    ("Lock", "Kilid"), ("Puzzle", "Tapmaca"), ("Smile", "Gülümsəmə"),
    ("MonitorSmartphone", "Monitor/Telefon"), ("Check", "Tik"), ("Star", "Ulduz"),
]


class SiteSettings(models.Model):
    """
    Tək sətirlik (singleton) cədvəl: brend, hero mətni, əlaqə məlumatları.
    Həmişə pk=1 ilə saxlanır — yeni sətir yaratmağa çalışsa belə, mövcud olan yenilənir.
    """
    brand_name = models.CharField(max_length=60, default="SERVIO")
    tagline = models.CharField(max_length=200, blank=True,
                                help_text="Loqonun yanında və ya footer-də qısa şüar")
    logo = models.ImageField(upload_to="site/", blank=True, null=True,
                              help_text="Boş saxlansa, hazırkı statik loqo işləyir")

    hero_title = models.CharField(max_length=200, default="Servisinizi daha rahat idarə edin.")
    hero_subtitle = models.TextField(
        blank=True,
        default="Müştərilər, təmirlər, gəlir-xərc, anbar, borclar və hesabatlar — "
                "hamısı bir platformada. Telefon və kompüter servis bizneslər üçün "
                "ağıllı idarəetmə sistemi.",
    )

    email = models.EmailField(default="info@servio.az")
    phone = models.CharField(max_length=32, default="+994 50 000 00 00")
    whatsapp = models.CharField(max_length=20, default="994500000000",
                                 help_text="wa.me üçün, + və boşluqsuz")
    address = models.CharField(max_length=200, default="Bakı, Azərbaycan")
    hours = models.CharField(max_length=120, default="Bazar ertəsi – Şənbə, 09:00 – 18:00")

    footer_note = models.CharField(max_length=200, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sayt ayarları"
        verbose_name_plural = "Sayt ayarları"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # tək sətir heç vaxt silinmir

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return self.brand_name


class OrderedContent(models.Model):
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True
        ordering = ["order", "id"]


class FaqItem(OrderedContent):
    question = models.CharField(max_length=255)
    answer = models.TextField()

    def __str__(self):
        return self.question


class FeatureItem(OrderedContent):
    """Ana səhifə + Funksiyalar səhifəsindəki funksiya kartları."""
    icon = models.CharField(max_length=30, choices=ICON_CHOICES, default="Check")
    tone = models.CharField(max_length=10, choices=[("primary", "Əsas (mavi)"), ("dark", "Tünd")],
                             default="primary")
    title = models.CharField(max_length=100)
    short_description = models.CharField(max_length=200, blank=True)
    points = models.TextField(blank=True, help_text="Hər sətirdə bir bənd")

    def points_list(self):
        return [p.strip() for p in self.points.splitlines() if p.strip()]

    def __str__(self):
        return self.title


class AboutValue(OrderedContent):
    """Haqqımızda səhifəsindəki "Yanaşmamız" dəyər kartları."""
    icon = models.CharField(max_length=30, choices=ICON_CHOICES, default="Check")
    title = models.CharField(max_length=100)
    text = models.TextField()

    def __str__(self):
        return self.title


class HomeStep(OrderedContent):
    """Ana səhifədəki "Necə işləyir" addımları."""
    number = models.CharField(max_length=5, default="1")
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.number}. {self.title}"
