from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import CashTransaction
from .oplog import write_log, cash_logs_suppressed


@receiver(pre_delete, sender=CashTransaction)
def log_cash_deletion(sender, instance, **kwargs):
    if cash_logs_suppressed():
        return
    write_log(
        instance.shop, "cash",
        f"{instance.get_type_display()} · {instance.description or instance.expense_category or '—'}",
        instance.amount,
        {
            "type": instance.type, "type_label": instance.get_type_display(), "method": instance.method,
            "amount": instance.amount, "description": instance.description,
            "expense_category": instance.expense_category, "created_at": instance.created_at,
            "repair_number": instance.repair.number if instance.repair_id else None,
        },
    )
