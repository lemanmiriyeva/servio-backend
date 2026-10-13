from django.db import models
from django.utils import timezone
from tenants.models import Shop, Branch
from accounts.models import User
from repairs.models import RepairOrder, PaymentMethod
from suppliers.models import Supplier


class TransactionType(models.TextChoices):
    # Etiket "Gəlir"dən "Kassa"ya dəyişdirilib (frontend-dəki Kassa səhifəsi ilə uyğun olsun deyə) —
    # bu, Django admin/Kapitan panelindəki seçim siyahısında görünən mətndir.
    INCOME = "income", "Kassa"
    EXPENSE = "expense", "Xərc"
    SUPPLIER_PAYMENT = "supplier_payment", "Təchizatçı ödənişi"
    REFUND = "refund", "Geri qaytarma (zəmanət)"
    # Xidmət ləğv edilən an, ona bağlı təchizatçı/usta ödənişi (SUPPLIER_PAYMENT) geri
    # alınır — sistem özü yaradır, əl ilə seçilmir (bax: repairs/serializers.py CANCELLED).
    EXPENSE_REFUND = "expense_refund", "Alışın geri qaytarılması (ləğv)"


class CashTransaction(models.Model):
    """Kassa səhifəsindəki hər sətir: gəlir, xərc və ya təchizatçıya ödəniş."""
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="cash_transactions")
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, related_name="cash_transactions")

    type = models.CharField(max_length=20, choices=TransactionType.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    description = models.CharField(max_length=255)

    repair = models.ForeignKey(RepairOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name="cash_entries")
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="cash_entries")
    expense_category = models.CharField(max_length=80, blank=True, help_text="Elektrik, İcarə, Maaş və s.")

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["shop", "type", "created_at"])]

    @property
    def signed_amount(self):
        return self.amount if self.type == TransactionType.INCOME else -self.amount

    def __str__(self):
        return f"{self.get_type_display()} · {self.amount}"


class CashboxOpeningBalance(models.Model):
    """Filialın başlanğıc kassa balansı (ay/dövr üçün)."""
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="opening_balances")
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="opening_balances")
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    as_of_date = models.DateField(default=timezone.now)

    class Meta:
        ordering = ["-as_of_date"]


def compute_cashbox_summary(shop):
    """
    Kassa səhifəsi VƏ ana səhifə eyni bu funksiyadan istifadə edir ki, 'kassa balansı'
    hər yerdə EYNİ (xərc/təchizatçı ödənişi düşülmüş) rəqəm olsun — ikisi arasında
    fərqli hesablama/sinxronsuzluq yaranmasın.

    "Kassa balansı" YALNIZ NAĞD (method="cash") əməliyyatları əhatə edir — kartla/bank
    köçürməsi ilə qəbul edilən pul fiziki kassada deyil (bankdadır), ona görə kartla
    ödəniş qəbul ediləndə "kassada bu qədər nağd pul var" rəqəmi süni şəkildə artmamalıdır
    (müştərinin konkret şikayəti elə bu idi: "kart seçəndə kassanın məbləğini qaldırır").
    Kartla/bankla olan hərəkətlər ayrıca "card_balance" olaraq hesablanır — ümumi
    gəlir/hesabat rəqəmlərinə (reports/views.py-dakı total_sales və s.) TƏSİR ETMİR,
    çünki onlar bu funksiyadan deyil, RepairOrder.sale_price-dan hesablanır.
    """
    from decimal import Decimal

    opening = CashboxOpeningBalance.objects.filter(shop=shop).order_by("-as_of_date").first()
    opening_amount = opening.amount if opening else Decimal("0")

    def totals(qs):
        income = sum((t.amount for t in qs.filter(type=TransactionType.INCOME)), Decimal("0"))
        expense = sum((t.amount for t in qs.filter(type=TransactionType.EXPENSE)), Decimal("0"))
        supplier_payment = sum((t.amount for t in qs.filter(type=TransactionType.SUPPLIER_PAYMENT)), Decimal("0"))
        refund = sum((t.amount for t in qs.filter(type=TransactionType.REFUND)), Decimal("0"))
        expense_refund = sum((t.amount for t in qs.filter(type=TransactionType.EXPENSE_REFUND)), Decimal("0"))
        return income, expense, supplier_payment, refund, expense_refund

    all_qs = CashTransaction.objects.filter(shop=shop)
    cash_qs = all_qs.filter(method=PaymentMethod.CASH)
    card_qs = all_qs.exclude(method=PaymentMethod.CASH)

    income, expense, supplier_payment, refund, expense_refund = totals(cash_qs)
    card_income, card_expense, card_supplier_payment, card_refund, card_expense_refund = totals(card_qs)

    return {
        "opening_balance": opening_amount,
        "income": income,
        "expense": expense,
        "supplier_payment": supplier_payment,
        "refund": refund,
        "expense_refund": expense_refund,
        "current_balance": opening_amount + income - expense - supplier_payment - refund + expense_refund,
        # Kartla/bank köçürməsi ilə olan NET hərəkət (nə qədər kartla qəbul edilib, nə qədər
        # kartla xərclənib) — məlumat üçün, "Kassa balansı"na daxil edilmir.
        "card_balance": card_income - card_expense - card_supplier_payment - card_refund + card_expense_refund,
    }


def assert_sufficient_balance(shop, amount, method=PaymentMethod.CASH):
    """
    Kassadan/kartdan pul çıxan hər əməliyyatdan (xərc, təchizatçı ödənişi) əvvəl çağırılır —
    balans kifayət deyilsə ValidationError qaldırır ki, balans mənfiyə düşməsin və
    istifadəçi "Kassada/Kartda vəsait yoxdur" mesajını görsün.

    DİQQƏT: `method` MÜTLƏQ ötürülməlidir — əvvəllər bu funksiya həmişə YALNIZ nağd
    balansını (current_balance) yoxlayırdı, "method" parametri heç olmayıb. Nəticədə
    kartla/bank köçürməsi ilə edilən xərc/ödəniş (məs. "Xərc" səhifəsində üsul=Kart
    seçəndə) səhvən nağd balansı ilə müqayisə olunurdu — nağd balans az olanda kartla
    ödəniş səbəbsiz rədd edilir, YA DA nağd balans kifayət olanda kart balansı həqiqətən
    kifayət etməsə belə əməliyyat keçib kart balansını mənfiyə salırdı.
    """
    from rest_framework.exceptions import ValidationError

    summary = compute_cashbox_summary(shop)
    if method == PaymentMethod.CASH:
        current = summary["current_balance"]
        label = "Kassada"
    else:
        current = summary["card_balance"]
        label = "Kart/bank balansında"
    if amount > current:
        # {"detail": ...} şəklində qaldırılır — kodun qalan hissəsində bu format
        # istifadə olunur (bax: repairs/[id]/page.tsx-də err.data.detail yoxlaması),
        # sadə mətn versə DRF onu massiv kimi qaytarır və frontend-dəki bu format
        # gözləyən yerlər mesajı tapa bilmir.
        raise ValidationError({
            "detail": f"{label} vəsait yoxdur — cari balans {current} AZN, bu əməliyyat {amount} AZN tələb edir."
        })