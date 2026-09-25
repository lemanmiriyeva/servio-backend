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


class SubscriptionPayment(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="subscription_payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_at = models.DateTimeField(default=timezone.now)
    period_start = models.DateField()
    period_end = models.DateField()

    class Meta:
        ordering = ["-paid_at"]

    def __str__(self):
        return f"{self.shop.name} · {self.amount}"
