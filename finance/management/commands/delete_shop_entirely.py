"""
Bir mağazanı (Shop) VƏ ONA BAĞLI HƏR ŞEYİ (müştərilər, istifadəçilər, təmirlər, kassa,
təchizatçılar, anbar) tam silir. wipe_transactional_data-dan fərqli olaraq, bu əmr
mağazanın ÖZÜNÜ də silir — heç nə qalmır.

Sıra vacibdir: RepairOrder.customer sahəsi PROTECT olduğu üçün Shop.delete() birbaşa
çağırılsa, Customer-lər (cascade ilə) silinməyə çalışılanda Django ProtectedError verir —
hətta RepairOrder-lərin özü də eyni cascade-də silinəcək olsa belə. Ona görə əvvəlcə
RepairOrder-ləri əl ilə silirik, sonra Shop.delete() qalan hər şeyi (Customer, Branch,
User, Role, Supplier, Product, CashTransaction, CashboxOpeningBalance) cascade ilə özü silir.

DİQQƏT: GERİ QAYTARILMAZDIR. Defolt --dry-run.

İSTİFADƏ:
    python manage.py delete_shop_entirely --shop <shop_id>            # dry-run
    python manage.py delete_shop_entirely --shop <shop_id> --apply    # faktiki silir
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from customers.models import Customer
from repairs.models import RepairOrder
from tenants.models import Shop

try:
    from accounts.models import User
except Exception:  # pragma: no cover
    User = None


class Command(BaseCommand):
    help = "Bir mağazanı və ona bağlı HƏR ŞEYİ (müştərilər, istifadəçilər daxil) tam silir."

    def add_arguments(self, parser):
        parser.add_argument("--shop", type=str, required=True, help="Shop id/UUID (məcburidir).")
        parser.add_argument("--apply", action="store_true", help="Faktiki sil (verilməsə, yalnız göstərir).")

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

        repair_count = RepairOrder.objects.filter(shop=shop).count()
        customer_count = Customer.objects.filter(shop=shop).count()
        user_count = User.objects.filter(shop=shop).count() if User else 0

        self.say(f"Mağaza: {shop.name} ({shop.pk})")
        self.say(f"  RepairOrder: {repair_count}")
        self.say(f"  Customer: {customer_count}")
        self.say(f"  User: {user_count}")
        self.say("  (+ bu mağazaya bağlı bütün Supplier, Product, CashTransaction, Branch, Role)")

        if not apply_changes:
            self.say("")
            self.say("Faktiki silmək üçün --apply əlavə edib yenidən işlət.", self.style.WARNING)
            return

        with transaction.atomic():
            # RepairOrder.customer PROTECT olduğu üçün əvvəlcə silinməlidir — əks halda
            # Shop.delete() Customer-ləri cascade ilə silməyə çalışanda ProtectedError verir.
            RepairOrder.objects.filter(shop=shop).delete()
            shop.delete()

        self.say("")
        self.say("SİLİNDİ — mağaza və ona bağlı hər şey.", self.style.SUCCESS)
