from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import RepairOrder, RepairStatusHistory


@receiver(post_save, sender=RepairOrder)
def log_initial_status(sender, instance, created, raw=False, **kwargs):
    """Təmir yaradılan kimi ilkin statusu (adətən 'Qəbul edildi') tarixçəyə yazır — əks halda
    status tarixçəsi yalnız SONRAKI dəyişikliklərdən (bax: RepairStatusUpdateSerializer) başlayardı
    və ilk statusun nə vaxt başladığı heç yerdə görünməzdi."""
    if raw or not created:
        return
    RepairStatusHistory.objects.create(repair=instance, status=instance.status, changed_at=instance.received_at)