"""
Bir mağazanın BÜTÜN əməliyyat (tranzaksiya) datasını silir — YALNIZ bunlar qalır:
  - Shop/Branch (mağaza özü)
  - User/Role (istifadəçilər)
  - Customer (müştərilər)

Silinən hər şey:
  - RepairOrder (və ona bağlı: RepairStatusHistory, RepairPayment, RepairWarrantyReturn,
    RepairPartUsage — hamısı cascade ilə avtomatik)
  - Supplier (və ona bağlı: SupplierPurchase, SupplierPurchasePayment — cascade ilə)
  - CashTransaction, CashboxOpeningBalance
  - Product (inventory) və ona bağlı StockMovement (cascade ilə)

Müştərilər (Customer) TOXUNULMAZ qalır — onlara bağlı repair_orders PROTECT olduğu üçün
əvvəlcə repair-lər silinməlidir (bu əmr bunu düzgün ardıcıllıqla edir).

DİQQƏT: Bu GERİ QAYTARILMAZ bir əməliyyatdır. Defolt olaraq --dry-run (heç nə silinmir,
yalnız nə qədər qeyd silinəcəyini göstərir). Faktiki silmək üçün --apply və --shop tələb olunur.

İSTİFADƏ:
    python manage.py wipe_transactional_data --shop <shop_id>            # dry-run, sayları göstərir
    python manage.py wipe_transactional_data --shop <shop_id> --apply    # faktiki silir
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from finance.models import CashTransaction, CashboxOpeningBalance
from inventory.models import Product
from repairs.models import RepairOrder
from suppliers.models import Supplier
from tenants.models import Shop


class Command(BaseCommand):
    help = "Bir mağazanın bütün təmir/kassa/təchizatçı/anbar datasını silir (mağaza, istifadəçi, müştəri qalır)."

    def add_arguments(self, parser):
        parser.add_argument("--shop", type=str, required=True, help="Shop id/UUID (məcburidir).")
        parser.add_argument("--apply", action="store_true", help="Faktiki sil (verilməsə, yalnız sayları göstərir).")

    def say(self, msg, style=None):
        try:
            self.stdout.write(style(msg) if style else msg)
        except UnicodeEncodeError:
            self.stdout.write(msg.encode("ascii", "replace").decode())

    def handle(self, *args, **opts):
        try:
            shop = Shop.objects.get(pk=opts["shop"])
        except Shop.DoesNotExist:
            raise CommandError(f"Shop tapılmadı: {opts['shop']}")

        apply_changes = opts["apply"]
        if not apply_changes:
            self.say("DRY-RUN rejimi (heç nə silinmir). Faktiki silmək üçün --apply əlavə et.", self.style.WARNING)

        self.say(f"Mağaza: {shop.name} ({shop.pk})")

        counts = {
            "RepairOrder": RepairOrder.objects.filter(shop=shop).count(),
            "Supplier": Supplier.objects.filter(shop=shop).count(),
            "CashTransaction": CashTransaction.objects.filter(shop=shop).count(),
            "CashboxOpeningBalance": CashboxOpeningBalance.objects.filter(shop=shop).count(),
            "Product": Product.objects.filter(shop=shop).count(),
        }
        for label, n in counts.items():
            self.say(f"  {label}: {n} qeyd {'silinəcək' if apply_changes else 'tapıldı'}")

        if not apply_changes:
            self.say("")
            self.say("Faktiki silmək üçün --apply əlavə edib yenidən işlət.", self.style.WARNING)
            return

        with transaction.atomic():
            # Sıra vacibdir: Customer.repair_orders PROTECT olduğu üçün əvvəlcə RepairOrder
            # silinməlidir; Supplier/Product/CashTransaction-un repair-ə FK-ları SET_NULL
            # olduğu üçün onlardan əvvəl silinsə də problem yoxdur, amma eyni ardıcıllıqla
            # gedirik ki, nəticə proqnozlaşdırıla bilən olsun.
            RepairOrder.objects.filter(shop=shop).delete()
            Supplier.objects.filter(shop=shop).delete()
            CashTransaction.objects.filter(shop=shop).delete()
            CashboxOpeningBalance.objects.filter(shop=shop).delete()
            Product.objects.filter(shop=shop).delete()

        self.say("")
        self.say("SİLİNDİ. Mağaza, istifadəçilər və müştərilər toxunulmadı.", self.style.SUCCESS)