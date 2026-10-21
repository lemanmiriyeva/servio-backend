from django.db.models.signals import post_save, pre_delete
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

@receiver(pre_delete, sender=RepairOrder)
def remove_repair_money_traces(sender, instance, **kwargs):
    """
    DÜZƏLİŞ ("müştərinin əməliyyatını sildim, amma Kassa və Hesablara təsir etmədi"):
    CashTransaction.repair və SupplierPurchase.repair `on_delete=SET_NULL`-dur — təmir
    silinəndə onun Kassa sətirləri və təchizatçı alışları SİLİNMİR, sadəcə "təmirsiz yetim"
    qalırdı. Nəticədə Kassa balansı da, təchizatçı borcu da dəyişmirdi (üstəlik bu yetim
    gəlir sətirləri Hesabatlarda "əl ilə əlavə edilən gəlir" kimi sayılırdı).
    `pre_delete` Django-nun SET_NULL addımından ƏVVƏL işləyir, ona görə bağlı qeydləri hələ
    tapa bilirik. Siqnal olduğu üçün hər silmə yolunda (Platforma paneli, API, shell) işləyir.
    """
    from finance.models import CashTransaction
    from finance.oplog import write_log, suppress_cash_logs
    from suppliers.models import SupplierPurchase

    cash_rows = list(CashTransaction.objects.filter(repair=instance))
    # Silinmiş əməliyyatlar jurnalı (Mağaza Admini üçün): silinməzdən ƏVVƏL tam "şəkil" saxlanılır.
    write_log(
        instance.shop, "repair",
        f"{instance.number} · {instance.customer.full_name} · {instance.device_brand} {instance.device_model}".strip(),
        instance.sale_price,
        {
            "number": instance.number, "customer": instance.customer.full_name, "phone": instance.customer.phone,
            "device": f"{instance.device_brand} {instance.device_model}".strip(),
            "issue": instance.issue_description, "status": instance.status,
            "sale_price": instance.sale_price, "cost_price": instance.cost_price,
            "paid_amount": instance.paid_amount, "received_at": instance.received_at,
            "payments": [{"amount": p.amount, "method": p.method, "paid_at": p.paid_at} for p in instance.payments.all()],
            "cash_entries": [{"type": t.get_type_display(), "amount": t.amount, "method": t.method,
                              "description": t.description} for t in cash_rows],
        },
    )
    with suppress_cash_logs():
        CashTransaction.objects.filter(repair=instance).delete()
    SupplierPurchase.objects.filter(repair=instance).delete()  # SupplierPurchasePayment cascade olur
