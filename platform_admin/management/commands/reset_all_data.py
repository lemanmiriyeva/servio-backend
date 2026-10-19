"""
DİQQƏT — ÇOX TƏHLÜKƏLİ KOMANDA.

Platformadakı BÜTÜN mağaza/müştəri/əməliyyat datasını (mağazalar, filiallar, müştərilər,
təmir sifarişləri, ödənişlər, anbar, təchizatçılar, kassa, marketplace, dəstək sorğuları,
abunə ödənişləri) VƏ BÜTÜN istifadəçiləri (mövcud superuser daxil) həmişəlik silir.

TOXUNULMUR (olduğu kimi qalır):
  - tenants.Plan                                    (Planlar/qiymətlər)
  - sitecontent.* (SiteSettings, HomeStep, FeatureItem, AboutValue, FaqItem)
    — sayt məzmunu: hero mətni, loqo/marka, əlaqə məlumatları, "necə işləyir" addımları,
    funksiya kartları, haqqımızda, FAQ

Silgidən sonra tək bir Platform Super Admin istifadəçisi yaradılır.

İstifadə:
    python3 manage.py reset_all_data --yes-i-am-sure

(--yes-i-am-sure bayrağı olmadan heç nə silinmir — təhlükəsizlik üçün.)
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

SUPERUSER_USERNAME = "Admin"
SUPERUSER_PASSWORD = "Ulduzl@r90"


class Command(BaseCommand):
    help = "BÜTÜN mağaza/istifadəçi/əməliyyat datasını silir (sayt məzmunu və planlar istisna) və yeni superuser yaradır."

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes-i-am-sure",
            action="store_true",
            help="Təhlükəsizlik üçün məcburidir — bu olmadan komanda heç nə etmir.",
        )

    def handle(self, *args, **options):
        if not options["yes_i_am_sure"]:
            raise CommandError(
                "Heç nə silinmədi. Əmin olduğunuzu təsdiq etmək üçün "
                "--yes-i-am-sure bayrağı ilə yenidən işə salın."
            )

        from inventory.models import RepairPartUsage, StockMovement, Product
        from repairs.models import (
            RepairWarrantyReturn, RepairStatusHistory, RepairPayment, RepairOrder,
        )
        from suppliers.models import SupplierPurchasePayment, SupplierPurchase, Supplier
        from customers.models import Customer
        from finance.models import CashTransaction, CashboxOpeningBalance
        from marketplace.models import MarketplaceOrder
        from platform_admin.models import SupportTicket, ContactInquiry, SubscriptionPayment
        from accounts.models import RolePermission, Role
        from tenants.models import Branch, Shop

        User = get_user_model()

        self.stdout.write(self.style.WARNING("Başlanır: bütün mağaza/istifadəçi datası silinir…"))

        with transaction.atomic():
            # Leaf-dən root-a doğru, FK on_delete konfiqurasiyasından asılı olmadan təhlükəsiz sıra.
            counts = {}
            for model in [
                RepairPartUsage, StockMovement,
                RepairWarrantyReturn, RepairStatusHistory, RepairPayment, RepairOrder,
                SupplierPurchasePayment, SupplierPurchase, Supplier,
                Product,
                CashTransaction, CashboxOpeningBalance,
                MarketplaceOrder,
                SupportTicket, ContactInquiry, SubscriptionPayment,
                Customer,
                RolePermission, Role,
                User,       # mövcud bütün istifadəçilər (superuser daxil)
                Branch,
                Shop,
            ]:
                deleted, _ = model.objects.all().delete()
                counts[model.__name__] = deleted

            superuser = User.objects.create_superuser(
                username=SUPERUSER_USERNAME,
                password=SUPERUSER_PASSWORD,
            )
            superuser.is_platform_admin = True
            superuser.save(update_fields=["is_platform_admin"])

        self.stdout.write(self.style.SUCCESS("Silindi:"))
        for name, n in counts.items():
            if n:
                self.stdout.write(f"  {name}: {n}")
        self.stdout.write(self.style.SUCCESS(
            f"Yeni Platform Super Admin yaradıldı → istifadəçi adı: {SUPERUSER_USERNAME!r}"
        ))
        self.stdout.write(self.style.SUCCESS(
            "Sayt məzmunu (sitecontent app) və Planlar (tenants.Plan) toxunulmadan qaldı."
        ))
