from django.db import models
from django.utils import timezone
from tenants.models import Shop


class SupportTicket(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Açıq"
        IN_PROGRESS = "in_progress", "İcra olunur"
        CLOSED = "closed", "Bağlanıb"

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="support_tickets")
    subject = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.subject


class ContactInquiry(models.Model):
    """İctimai saytdakı '/elaqe' formundan göndərilən sorğular — hələ müştəri olmayan,
    sadəcə maraqlanan insanlar. Baş Adminin paneldə 'Müştəri sorğuları' bölməsində görünür."""

    class Status(models.TextChoices):
        NEW = "new", "Yeni"
        CONTACTED = "contacted", "Əlaqə saxlanıldı"
        CLOSED = "closed", "Bağlanıb"

    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=32)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.full_name} · {self.phone}"


class SubscriptionPayment(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="subscription_payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_at = models.DateTimeField(default=timezone.now)
    # `blank=True` — abunə dövrü həmişə 1 aydır (bax: Shop.reactivate), ona görə Baş Admin bunları
    # əl ilə hesablamaq məcburiyyətində deyil: boş buraxılsa, save() ödəniş tarixindən 1 ay kimi
    # avtomatik doldurur.
    period_start = models.DateField(blank=True)
    period_end = models.DateField(blank=True)

    class Meta:
        ordering = ["-paid_at"]

    def save(self, *args, **kwargs):
        if not self.period_start:
            self.period_start = (self.paid_at.date() if hasattr(self.paid_at, "date") else self.paid_at) or timezone.now().date()
        if not self.period_end:
            self.period_end = self.period_start + timezone.timedelta(days=30)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.shop.name} · {self.amount}"