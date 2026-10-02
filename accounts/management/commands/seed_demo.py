import getpass

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from accounts.models import Role, RolePermission, User
from customers.models import Customer
from finance.models import CashboxOpeningBalance, CashTransaction
from inventory.models import Product, RepairPartUsage, StockMovement
from marketplace.models import MarketplaceOrder
from platform_admin.models import SubscriptionPayment, SupportTicket
from repairs.models import RepairOrder, RepairPayment
from suppliers.models import Supplier, SupplierPurchase
from tenants.models import Branch, Plan, Shop


class Command(BaseCommand):
    help = (
        "TƏHLÜKƏLİ: bazadakı BÜTÜN məlumatı (bütün mağazalar, istifadəçilər, təmirlər, "
        "müştərilər, anbar, kassa, təchizatçılar, marketplace, dəstək müraciətləri — "
        "hər şey) GERİ QAYTARILMAZ şəkildə silir və yalnız 1 ədəd superadmin yaradır. "
        "Production serverini ilk dəfə canlıya buraxmazdan əvvəl təmiz başlanğıc üçün istifadə olunur."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes", action="store_true",
            help="Təsdiq sorğusu olmadan birbaşa icra et (ehtiyatlı istifadə et!)",
        )
        parser.add_argument("--username", default="admin", help="Superadmin istifadəçi adı (default: admin)")
        parser.add_argument("--email", default="infoservio2026@gmail.com", help="Superadmin e-poçtu")
        parser.add_argument(
            "--password", default=None,
            help="Superadmin parolu. Verilməsə, təhlükəsiz şəkildə terminalda soruşulacaq.",
        )

    # Windows konsolu bəzən ə/ı/ş çap edə bilmir — çap xətası skripti dayandırmasın.
    def say(self, msg, style=None):
        try:
            self.stdout.write(style(msg) if style else msg)
        except UnicodeEncodeError:
            self.stdout.write(msg.encode("ascii", "replace").decode())

    # ------------------------------------------------------------------ main
    @transaction.atomic
    def handle(self, *args, **opts):
        if not opts["yes"]:
            self.say(
                "Bu əməliyyat bazadakı BÜTÜN məlumatı (bütün mağazalar, istifadəçilər, "
                "təmirlər, müştərilər, anbar, kassa və s.) GERİ QAYTARILMAZ şəkildə siləcək "
                "və yalnız 1 superadmin yaradacaq.",
                self.style.WARNING,
            )
            confirm = input("Davam etmək üçün böyük hərflərlə 'BƏLİ' yazın: ")
            if confirm.strip() != "BƏLİ":
                raise CommandError("Ləğv edildi — heç nə dəyişdirilmədi.")

        self.wipe_everything()

        password = opts["password"] or self.read_password()
        admin = self.create_superadmin(opts["username"], opts["email"], password)

        self.say("")
        self.say("Baza tam sıfırlandı — yalnız 1 superadmin qaldı:", self.style.SUCCESS)
        self.say(f"  İstifadəçi adı: {admin.username}")
        self.say(f"  E-poçt:         {admin.email}")
        self.say("")

    # ------------------------------------------------------------------ password
    def read_password(self):
        while True:
            pw = getpass.getpass("Superadmin üçün parol yaz: ")
            if len(pw) < 8:
                self.say("Parol ən azı 8 simvol olmalıdır, yenidən yaz.", self.style.ERROR)
                continue
            pw2 = getpass.getpass("Parolu təsdiq üçün təkrar yaz: ")
            if pw != pw2:
                self.say("Parollar üst-üstə düşmür, yenidən cəhd et.", self.style.ERROR)
                continue
            return pw

    # ------------------------------------------------------------------ wipe
    def wipe_everything(self):
        """Bütün cədvəllər — accounts və tenants daxil olmaqla — tam təmizlənir.
        Sıra PROTECT əlaqələrinə görə seçilib (əvvəlcə asılı/uşaq cədvəllər)."""
        models_in_order = [
            MarketplaceOrder,       # product -> PROTECT
            RepairPartUsage,        # product -> PROTECT
            StockMovement,
            Product,
            CashTransaction,
            CashboxOpeningBalance,
            RepairPayment,
            RepairOrder,            # customer -> PROTECT
            Customer,
            SupplierPurchase,
            Supplier,
            SupportTicket,
            SubscriptionPayment,
            User,                   # shop/branch/role -> silinməzdən əvvəl
            RolePermission,
            Role,                   # shop -> silinməzdən əvvəl
            Branch,
            Shop,
            Plan,
        ]
        for model in models_in_order:
            model.objects.all().delete()

        # id-lər 1-dən yenidən başlasın (yalnız sqlite-da aktualdır; mssql-də IDENTITY
        # avtomatik davam edir, problem yaratmır):
        if connection.vendor == "sqlite":
            tables = [m._meta.db_table for m in models_in_order]
            with connection.cursor() as cur:
                cur.executemany("DELETE FROM sqlite_sequence WHERE name = %s", [(t,) for t in tables])

        self.say(
            "Köhnə məlumatın hamısı silindi: mağazalar, filiallar, rollar, istifadəçilər, "
            "müştərilər, təmirlər, anbar, kassa, təchizatçılar, marketplace, dəstək müraciətləri."
        )

    # ------------------------------------------------------------------ superadmin
    def create_superadmin(self, username, email, password):
        user = User.objects.filter(username=username).first()
        if user is None:
            user = User(username=username)
        user.first_name, user.last_name = "Bas", "Admin"
        user.email = email
        user.is_platform_admin = True
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()
        return user