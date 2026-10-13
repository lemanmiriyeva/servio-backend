"""
Mağazanın kassa düzəlişlərindən (bax: finance/models.py, suppliers/views.py, repairs/serializers.py-dəki
izahlar) ƏVVƏL yaradılmış "köhnə" qeydlər üçün — kod düzəlişi yalnız BUNDAN SONRA yaradılan
əməliyyatlara tətbiq olunur, artıq bazada olan qeydləri özü-özünə düzəltmir. Bu əmr mövcud
(real) müştəri/təmir/təchizatçı datasını SİLMİR və YENİDƏN YARATMIR — yalnız o qeydlərə aid,
əvvəllər YARADILMAMIŞ kassa (CashTransaction) yazılarını əlavə edir ki, Kassa balansı və
Hesabatlar bu köhnə qeydlər üçün də düzgün (indiki məntiqlə üst-üstə düşən) rəqəm versin.

Düzəldilən 3 konkret ssenari:
  1) Təchizatçı alışı ilə BİRGƏ dərhal ödənilən məbləğ üçün Kassa yazısı yox idi (#53-ün
     köhnə data üçün versiyası) — hər təchizatçı üzrə "ödənilmiş məbləğ" ilə "artıq Kassaya
     yazılmış təchizatçı ödənişi" arasındaki fərq bir "backfill" SUPPLIER_PAYMENT yazısı kimi
     əlavə edilir.
  2) Xarici ustaya (technician_name, Supplier seçilmədən) ödənilən cost_price heç vaxt Kassaya
     xərc kimi yazılmayıb — hər belə təmir üçün, hələ heç bir kassa yazısı yoxdursa, bir
     SUPPLIER_PAYMENT yazısı əlavə edilir.
  3) Təmir artıq LƏĞV EDİLİB, amma ləğv olunduğu anda bu kod hələ yox idi — ona görə müştəri
     ödənişi geri qaytarılmayıb və/və ya təchizatçı/usta ödənişi geri alınmayıb. Hər ləğv
     edilmiş təmir üçün indiki ləğv-məntiqi (bax: RepairStatusUpdateSerializer.save) tətbiq
     olunur, əskik olan REFUND/EXPENSE_REFUND yazıları əlavə edilir.

İdempotentdir — artıq düzgün olan qeydlər üçün heç nə yaratmır, təkrar işlədilsə heç nəyi
ikiqat yazmır (hər dəfə mövcud vəziyyəti yenidən hesablayır).

İSTİFADƏ:
    python manage.py backfill_cash_corrections            # --dry-run defolt (HEÇ NƏ YAZMIR, yalnız göstərir)
    python manage.py backfill_cash_corrections --apply     # faktiki yazır (tək dəfə, tranzaksiya daxilində)
    python manage.py backfill_cash_corrections --apply --shop <shop_id>   # yalnız bir mağaza üçün
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from finance.models import CashTransaction, TransactionType
from repairs.models import RepairOrder, RepairStatus
from suppliers.models import Supplier, PurchaseStatus
from tenants.models import Shop


class Command(BaseCommand):
    help = "Kassa düzəlişlərindən əvvəl yaradılmış köhnə qeydlər üçün əskik CashTransaction yazılarını bərpa edir."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                             help="Faktiki yaz (verilməsə, yalnız nə ediləcəyini göstərir, bazaya toxunmur).")
        parser.add_argument("--shop", type=str, default=None, help="Yalnız bu mağaza (Shop id/UUID) üçün işlə.")

    def say(self, msg, style=None):
        try:
            self.stdout.write(style(msg) if style else msg)
        except UnicodeEncodeError:
            self.stdout.write(msg.encode("ascii", "replace").decode())

    def handle(self, *args, **opts):
        apply_changes = opts["apply"]
        shops = Shop.objects.all()
        if opts["shop"]:
            shops = shops.filter(pk=opts["shop"])

        if not apply_changes:
            self.say("DRY-RUN rejimi (heç nə yazılmır). Faktiki tətbiq üçün --apply əlavə et.", self.style.WARNING)

        total_created = 0
        for shop in shops:
            with transaction.atomic():
                created = self.fix_shop(shop, apply_changes)
                total_created += created
                if not apply_changes:
                    # dry-run-da belə transaction.atomic() daxilində yaratdıq (yoxlamaq üçün) — geri qaytar
                    transaction.set_rollback(True)

        self.say("")
        self.say(f"YEKUN: {total_created} əskik kassa yazısı {'YARADILDI' if apply_changes else 'tapıldı (yaradılMADI — dry-run)'}.",
                  self.style.SUCCESS if apply_changes else self.style.WARNING)

    # ------------------------------------------------------------------
    def fix_shop(self, shop, apply_changes):
        created = 0
        created += self.fix_supplier_payments(shop, apply_changes)
        created += self.fix_technician_payouts(shop, apply_changes)
        created += self.fix_cancelled_repairs(shop, apply_changes)
        return created

    # ---------- 1) Təchizatçı alışı ilə birgə ödənilən, Kassaya yazılmamış məbləğlər ----------
    def fix_supplier_payments(self, shop, apply_changes):
        created = 0
        for supplier in Supplier.objects.filter(shop=shop):
            total_paid = sum(
                (p.paid_amount for p in supplier.purchases.exclude(status=PurchaseStatus.CANCELLED)),
                Decimal("0"),
            )
            already_posted = sum(
                (t.amount for t in CashTransaction.objects.filter(
                    shop=shop, type=TransactionType.SUPPLIER_PAYMENT, supplier=supplier)),
                Decimal("0"),
            )
            missing = total_paid - already_posted
            if missing > 0:
                self.say(f"  [Təchizatçı] {shop.name} / {supplier.name}: {missing} AZN kassaya yazılmamış ödəniş tapıldı.")
                if apply_changes:
                    CashTransaction.objects.create(
                        shop=shop, type=TransactionType.SUPPLIER_PAYMENT, amount=missing, method="cash",
                        description=f"{supplier.name} — köhnə alış ödənişi (geriyə bərpa edildi)",
                        supplier=supplier,
                    )
                created += 1
        return created

    # ---------- 2) Xarici ustaya (Supplier olmadan) ödənilən, Kassaya heç vaxt yazılmamış məbləğ ----------
    def fix_technician_payouts(self, shop, apply_changes):
        """
        DİQQƏT: yalnız dəqiq expense_category="Xarici usta ödənişi" yazısını axtarmırıq —
        köhnə (düzəlişdən əvvəlki) kodda bu məbləğ eyni repair-ə bağlı, amma BAŞQA/boş
        expense_category ilə artıq yazıla bilərdi (Supplier seçilmədən, usta ödənişi kimi).
        Ona görə bu repair üçün artıq Supplier-siz (supplier=None) SUPPLIER_PAYMENT/EXPENSE
        cəmi cost_price-a bərabər və ya çoxdursa, "artıq ödənilib" sayıb YENİ yazı YARATMIRIQ —
        əks halda eyni məbləği ikinci dəfə yazıb ikiqat kassa çıxışı yaradardıq.
        """
        created = 0
        qs = RepairOrder.objects.filter(shop=shop).exclude(technician_name="").exclude(cost_price=0)
        for repair in qs:
            already_posted = sum(
                (t.amount for t in CashTransaction.objects.filter(
                    shop=shop, repair=repair, supplier__isnull=True,
                    type__in=[TransactionType.SUPPLIER_PAYMENT, TransactionType.EXPENSE])),
                Decimal("0"),
            )
            if already_posted >= repair.cost_price:
                continue
            missing = repair.cost_price - already_posted
            self.say(f"  [Xarici usta] {shop.name} / {repair.number}: {missing} AZN "
                     f"({repair.technician_name}) kassaya yazılmamışdı.")
            if apply_changes:
                CashTransaction.objects.create(
                    shop=shop, branch=repair.branch, type=TransactionType.SUPPLIER_PAYMENT,
                    amount=missing, method="cash", expense_category="Xarici usta ödənişi",
                    description=f"{repair.number}, {repair.customer.full_name} — ustaya "
                                f"({repair.technician_name}) ödənildi (köhnə qeyd, geriyə bərpa edildi)",
                    repair=repair,
                )
            created += 1
        return created

    # ---------- 3) Artıq ləğv edilmiş, amma kassası geri qaytarılmamış təmirlər ----------
    def fix_cancelled_repairs(self, shop, apply_changes):
        created = 0
        for repair in RepairOrder.objects.filter(shop=shop, status=RepairStatus.CANCELLED):
            net_received = sum(
                (t.amount if t.type == TransactionType.INCOME else -t.amount)
                for t in CashTransaction.objects.filter(
                    shop=shop, repair=repair, type__in=[TransactionType.INCOME, TransactionType.REFUND])
            )
            if net_received > 0:
                self.say(f"  [Ləğv — müştəri] {shop.name} / {repair.number}: {net_received} AZN "
                         f"müştəriyə geri qaytarılmamışdı.")
                if apply_changes:
                    CashTransaction.objects.create(
                        shop=shop, branch=repair.branch, type=TransactionType.REFUND,
                        amount=net_received, method="cash",
                        description=f"{repair.number}, {repair.customer.full_name} — ləğv edilmiş xidmət, "
                                    f"ödəniş geri qaytarıldı (köhnə qeyd, geriyə bərpa edildi)",
                        repair=repair,
                    )
                created += 1

            paid_out = sum(
                (t.amount for t in CashTransaction.objects.filter(
                    shop=shop, repair=repair, type__in=[TransactionType.SUPPLIER_PAYMENT, TransactionType.EXPENSE])),
                Decimal("0"),
            )
            already_recovered = sum(
                (t.amount for t in CashTransaction.objects.filter(
                    shop=shop, repair=repair, type=TransactionType.EXPENSE_REFUND)),
                Decimal("0"),
            )
            to_recover = paid_out - already_recovered
            if to_recover > 0:
                self.say(f"  [Ləğv — təchizatçı/usta] {shop.name} / {repair.number}: {to_recover} AZN "
                         f"geri alınmamışdı.")
                if apply_changes:
                    CashTransaction.objects.create(
                        shop=shop, branch=repair.branch, type=TransactionType.EXPENSE_REFUND,
                        amount=to_recover, method="cash",
                        description=f"{repair.number}, {repair.customer.full_name} — ləğv edilmiş xidmət, "
                                    f"təchizatçı/ustaya ödənilən məbləğ geri alındı (köhnə qeyd, geriyə bərpa edildi)",
                        repair=repair,
                    )
                created += 1
        return created
