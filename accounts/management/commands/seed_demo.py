import datetime
import re
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from accounts.models import Module, Role, RolePermission, User
from customers.models import Customer
from finance.models import CashboxOpeningBalance, CashTransaction, TransactionType
from inventory.models import MovementType, Product, RepairPartUsage, StockMovement
from marketplace.models import MarketplaceOrder
from platform_admin.models import SubscriptionPayment, SupportTicket
from repairs.models import (
    PaymentMethod, PaymentStatus, RepairOrder, RepairPayment, RepairStatus,
)
from suppliers.models import Supplier, SupplierPurchase
from tenants.models import Branch, Plan, Shop

CASH, CARD, BANK = PaymentMethod.CASH, PaymentMethod.CARD, PaymentMethod.BANK_TRANSFER


def skeleton(text: str) -> str:
    """Yalnız ASCII hərf/rəqəm — 'tələbə (stajçı)' və pozuq 't?l?b? (staj??)' eyni nəticə verir."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def ago(days=0, hours=0):
    return timezone.now() - datetime.timedelta(days=days, hours=hours)


class Command(BaseCommand):
    help = "Demo məlumatı yükləyir. accounts cədvəllərinə toxunmur. --reset: əvvəlcə qalan cədvəlləri boşaldır."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true",
            help="accounts/tenants xaric bütün cədvəlləri boşalt və yenidən doldur",
        )

    # Windows konsolu bəzən ə/ı/ş çap edə bilmir — çap xətası seed-i dayandırmasın.
    def say(self, msg, style=None):
        try:
            self.stdout.write(style(msg) if style else msg)
        except UnicodeEncodeError:
            self.stdout.write(msg.encode("ascii", "replace").decode())

    # ------------------------------------------------------------------ main
    @transaction.atomic
    def handle(self, *args, **opts):
        has_data = any(m.objects.exists() for m in (Customer, RepairOrder, Product, Supplier, CashTransaction))
        if has_data and not opts["reset"]:
            raise CommandError(
                "Bazada artıq məlumat var. Üstündən yazmaq üçün: python manage.py seed_demo --reset"
            )
        if opts["reset"]:
            self.wipe()

        pro, _ = Plan.objects.get_or_create(name="Pro", defaults=dict(price_monthly=49, max_branches=5, max_users=15))
        Plan.objects.get_or_create(name="Basic", defaults=dict(price_monthly=19, max_branches=1, max_users=3))
        starter, _ = Plan.objects.get_or_create(name="Starter", defaults=dict(price_monthly=0, max_branches=1, max_users=2))

        admin = self.ensure_platform_admin()

        shop1, branch1, owner1 = self.ensure_shop(
            code="techfix", name="TechFix Servis", owner_name=("Elvin", "Hüseynov"), username="elvin.techfix",
            email="elvin@techfix.az", phone="+994501112233", city="Bakı", branch_name="Nəsimi filialı", plan=pro,
            extra=dict(
                address="Nəsimi rayonu, 28 May küçəsi 14, Bakı", phone="+994124445566",
                work_hours="B.e – Şənbə 10:00–19:00",
            ),
        )
        shop2, branch2, owner2 = self.ensure_shop(
            code="mobiltemir-gence", name="MobilTəmir Gəncə", owner_name=("Vüqar", "Hacıyev"),
            username="vuqar.mobiltemir", email="vuqar@mobiltemir.az", phone="+994552223344", city="Gəncə",
            branch_name="Mərkəz filialı", plan=pro,
            extra=dict(address="Nizami prospekti 52, Gəncə", phone="+994222556677", work_hours="B.e – B. 09:00–18:00"),
        )
        # Videoda "Platforma" bölməsinin boş görünməməsi üçün statusu fərqli 2 əlavə mağaza:
        shop3, branch3, owner3 = self.ensure_shop(
            code="quickfix-sumqayit", name="QuickFix Sumqayıt", owner_name=("Elşən", "Bağırov"),
            username="elsen.quickfix", email="elsen@quickfix.az", phone="+994557778899", city="Sumqayıt",
            branch_name="Mərkəz filialı", plan=starter,
            extra=dict(address="Zavodlar küçəsi 3, Sumqayıt", phone="+994186623344", work_hours="B.e – Ş. 10:00–18:00"),
            status=Shop.Status.TRIAL,
        )
        shop4, branch4, owner4 = self.ensure_shop(
            code="repairpoint-seki", name="Repair Point Şəki", owner_name=("Aynur", "Vəliyeva"),
            username="aynur.repairpoint", email="aynur@repairpoint.az", phone="+994703334455", city="Şəki",
            branch_name="Mərkəz filialı", plan=pro,
            extra=dict(address="M.Ə.Rəsulzadə küçəsi 9, Şəki", phone="+994242554433", work_hours="B.e – C. 09:00–18:00"),
            status=Shop.Status.OVERDUE,
        )

        self.seed_techfix(shop1, branch1, owner1)
        self.seed_gence(shop2, branch2, owner2)
        self.seed_small_shop(shop3, branch3, owner3, prefix="qf")
        self.seed_small_shop(shop4, branch4, owner4, prefix="rp")
        self.seed_marketplace(shop1, branch1, owner1, shop2, branch2, owner2)
        self.seed_platform(shop1, shop2, shop3, shop4, pro)

        self.say("")
        self.say("Demo məlumatı hazırdır (hərflər UTF-8 ilə yazıldı).", self.style.SUCCESS)
        self.say("")
        self.say("VİDEO ÜÇÜN ƏSAS GİRİŞ (yadda saxlamaq asandır):")
        self.say("  Mağaza paneli:    demo / demo1234   (TechFix Servis, Bakı — Sahib, hər şeyə icazəli)")
        self.say("  Platforma paneli: admin / admin1234  (Bas Admin, Superuser — BÜTÜN mağazaları idarə edir)")
        self.say("")
        self.say("Hər mağazanın öz Platforma girişi (is_shop_admin=True — yalnız öz mağazasını görür):")
        self.say("  elvin.techfix / parol123      — TechFix Servis (Bakı)")
        self.say("  vuqar.mobiltemir / parol123   — MobilTəmir Gəncə")
        self.say("  elsen.quickfix / parol123     — QuickFix Sumqayıt")
        self.say("  aynur.repairpoint / parol123  — Repair Point Şəki")
        self.say("")
        self.say("Digər nümunə istifadəçilər (TechFix, rol/status müxtəlifliyi üçün):")
        self.say("  rustem.usta / parol123    — Usta (aktiv)")
        self.say("  zeyneb.kassir / parol123  — Kassir (aktiv)")
        self.say("  orxan.anbar / parol123    — Anbardar (aktiv)")
        self.say("  nermin.staj / parol123    — tələbə/stajçı (aktiv)")
        self.say("  vasif.usta / parol123     — Usta (dəvət göndərilib, hələ giriş etməyib)")
        self.say("  kamran.usta / parol123    — Usta (deaktiv edilmiş keçmiş işçi)")
        self.say("")
        self.say("Mağazalar: TechFix (aktiv), MobilTəmir Gəncə (aktiv), QuickFix Sumqayıt (sınaq), "
                  "Repair Point Şəki (ödəniş gecikib)")
        self.say(
            f"  Təmir: {RepairOrder.objects.count()}, müştəri: {Customer.objects.count()}, "
            f"məhsul: {Product.objects.count()}, kassa əməliyyatı: {CashTransaction.objects.count()}, "
            f"marketplace sifarişi: {MarketplaceOrder.objects.count()}, istifadəçi: {User.objects.count()}"
        )

    # ------------------------------------------------------------------ wipe
    def wipe(self):
        """accounts və tenants XARİC hər şey. Sıra PROTECT əlaqələrinə görə seçilib."""
        models_in_order = [
            MarketplaceOrder,  # product -> PROTECT
            RepairPartUsage,  # product -> PROTECT
            StockMovement,
            Product,
            CashTransaction,
            CashboxOpeningBalance,
            RepairOrder,  # ödənişlər CASCADE; digər FK-lər SET_NULL
            Customer,  # RepairOrder.customer -> PROTECT (təmirlər artıq silinib)
            SupplierPurchase,
            Supplier,
            SupportTicket,
            SubscriptionPayment,
        ]
        for model in models_in_order:
            model.objects.all().delete()
        # RepairPayment RepairOrder ilə birlikdə CASCADE silinir; id-lər 1-dən başlasın:
        if connection.vendor == "sqlite":
            tables = [m._meta.db_table for m in models_in_order] + [RepairPayment._meta.db_table]
            with connection.cursor() as cur:
                cur.executemany("DELETE FROM sqlite_sequence WHERE name = %s", [(t,) for t in tables])
        self.say("Köhnə məlumat təmizləndi (accounts və mağaza/filial saxlanıldı).")

    # ---------------------------------------------- shop/accounts: yalnız düzəlt
    def ensure_platform_admin(self):
        """Bas Admin — platforma panelində hər şeyi idarə edir. Video üçün sadə giriş: admin / admin1234."""
        user = User.objects.filter(username="admin").first()
        if user is None:
            user = User(username="admin")
        user.first_name, user.last_name = "Bas", "Admin"
        user.email = "admin@serviscrm.az"
        user.is_platform_admin = True
        user.is_staff = True
        user.is_superuser = True
        user.set_password("admin1234")
        user.save()
        return user

    def ensure_shop(self, *, code, name, owner_name, username, email, phone, city, branch_name, plan, extra,
                     status=Shop.Status.ACTIVE):
        shop, _ = Shop.objects.get_or_create(code=code, defaults=dict(name=name, plan=plan))
        shop.name, shop.city, shop.plan = name, city, plan
        shop.owner_full_name = " ".join(owner_name)
        shop.owner_phone, shop.owner_email = phone, email
        shop.status = status
        shop.default_warranty_days = shop.default_warranty_days or 14
        shop.logo_initials = "".join(w[0] for w in name.split()[:2]).upper()
        shop.next_payment_at = timezone.now().date() + datetime.timedelta(
            days=-3 if status == Shop.Status.OVERDUE else 12
        )
        if status == Shop.Status.TRIAL:
            shop.trial_ends_at = timezone.now().date() + datetime.timedelta(days=9)
        for k, v in extra.items():
            setattr(shop, k, v)
        shop.save()

        branch = shop.branches.filter(is_main=True).first() or Branch(shop=shop, is_main=True)
        branch.name = branch_name
        branch.address = extra.get("address", "")
        branch.phone = extra.get("phone", "")
        branch.save()

        owner_role = self.ensure_role(shop, "Admin / Sahib", is_owner=True)

        user = User.objects.filter(username=username).first()
        if user is None:
            user = User.objects.create_user(
                username=username, password="parol123", shop=shop, branch=branch, role=owner_role,
            )
        # Parola və rol toxunulmaz; yalnız mətn sahələri düzəlir
        user.first_name, user.last_name = owner_name
        user.email, user.phone = email, phone
        # Hər mağazanın öz "Platforma" girişi olsun deyə (yalnız öz mağazasını görür/idarə edir) —
        # Rol sistemindən (Sahib/Usta və s.) tamam ayrı, sırf bu məqsəd üçün olan müstəqil bayraq.
        user.is_shop_admin = True
        user.save(update_fields=["first_name", "last_name", "email", "phone", "is_shop_admin"])
        return shop, branch, user

    def staff_user(self, shop, branch, *, username, first, last, role, password="parol123",
                    status=User.Status.ACTIVE, phone=""):
        """İşçi hesabı (usta, kassir, anbardar, stajçı ...) — idempotent, mövcuddursa yalnız mətni düzəldir."""
        user = User.objects.filter(username=username).first()
        if user is None:
            user = User.objects.create_user(username=username, password=password, shop=shop, branch=branch, role=role)
        user.first_name, user.last_name, user.role, user.phone, user.status = first, last, role, phone, status
        user.save(update_fields=["first_name", "last_name", "role", "phone", "status"])
        return user

    def ensure_role(self, shop, name, *, is_owner=False, allowed=None):
        roles = list(Role.objects.filter(shop=shop, is_owner_role=is_owner).order_by("id"))
        role = next((r for r in roles if r.name == name), None) \
               or next((r for r in roles if skeleton(r.name) == skeleton(name)), None)
        if role:  # var — yalnız adı düzəlt (icazələrə toxunma)
            if role.name != name:
                role.name = name
                role.save(update_fields=["name"])
            return role
        role = Role.objects.create(shop=shop, name=name, is_owner_role=is_owner)
        if allowed is not None:
            for m in Module.values:
                RolePermission.objects.update_or_create(role=role, module=m, defaults={"is_allowed": m in allowed})
        return role

    # ------------------------------------------------------------ helpers
    def income(self, shop, branch, user, amount, method, when, desc, repair=None):
        CashTransaction.objects.create(
            shop=shop, branch=branch, type=TransactionType.INCOME, amount=amount, method=method,
            description=desc, repair=repair, created_by=user, created_at=when,
        )

    def repair(self, shop, branch, user, customer, *, brand, model, issue, cost, sale, status, received,
               delivered=None, warranty=0, payments=(), debt_due=None, imei="", work_done=""):
        r = RepairOrder.objects.create(
            shop=shop, branch=branch, customer=customer, device_brand=brand, device_model=model, device_imei=imei,
            issue_description=issue, work_done_note=work_done, cost_price=cost, sale_price=sale, status=status,
            received_at=received, delivered_at=delivered, warranty_days=warranty,
            warranty_started_at=delivered.date() if delivered and warranty else None,
            debt_due_date=debt_due, created_by=user,
        )
        RepairOrder.objects.filter(pk=r.pk).update(created_at=received)
        paid = Decimal("0")
        for amount, method, when in payments:
            RepairPayment.objects.create(repair=r, amount=amount, method=method, paid_at=when, received_by=user)
            self.income(shop, branch, user, amount, method, when, f"{r.number}, {customer.full_name}", repair=r)
            paid += Decimal(amount)
        if status == RepairStatus.CANCELLED or paid == 0:
            ps = PaymentStatus.UNPAID
        elif paid >= sale:
            ps = PaymentStatus.PAID
        elif delivered:
            ps = PaymentStatus.DEBT  # təhvil verilib, qalıq borc var
        else:
            ps = PaymentStatus.PARTIAL
        RepairOrder.objects.filter(pk=r.pk).update(payment_status=ps)
        r.refresh_from_db()
        return r

    def product(self, shop, name, brand, category, sku, qty, cost, price, *, min_alert=2, shared=False, mp_price=None):
        p = Product.objects.create(
            shop=shop, name=name, brand=brand, category=category, sku=sku, min_stock_alert=min_alert,
            unit_cost=cost, unit_sale_price=price, is_shared_to_marketplace=shared, marketplace_price=mp_price,
        )
        if qty:
            StockMovement.objects.create(
                shop=shop, product=p, movement_type=MovementType.PURCHASE_IN, quantity_delta=qty,
                note="İlkin anbar doldurulması", created_at=ago(days=28),
            )
        return p

    def use_part(self, repair, product, qty=1):
        RepairPartUsage.objects.create(repair=repair, product=product, quantity=qty)
        StockMovement.objects.filter(related_repair=repair, product=product).update(created_at=repair.received_at)

    # ---------------------------------------------------------- TechFix Bakı
    def seed_techfix(self, shop, branch, owner):
        owner_role = shop.roles.get(is_owner_role=True)
        usta_role = self.ensure_role(shop, "Usta", allowed=set(Module.values) - {Module.SETTINGS, Module.USERS})
        kassir_role = self.ensure_role(shop, "Kassir", allowed={Module.CASHBOX, Module.EXPENSES, Module.DEBTS, Module.CUSTOMERS})
        anbardar_role = self.ensure_role(shop, "Anbardar", allowed={Module.INVENTORY, Module.MARKETPLACE, Module.SUPPLIERS})
        stajci_role = self.ensure_role(shop, "tələbə (stajçı)", allowed={Module.REPAIRS, Module.CUSTOMERS, Module.INVENTORY})

        # Video üçün əsas hesab: eyni mağazada, sahib rolunda, sadə giriş.
        self.staff_user(shop, branch, username="demo", first="Demo", last="Hesabı", role=owner_role,
                         password="demo1234", phone="+994500000000")

        self.staff_user(shop, branch, username="rustem.usta", first="Rüstəm", last="Kərimov", role=usta_role,
                         phone="+994557001122")
        self.staff_user(shop, branch, username="zeyneb.kassir", first="Zeynəb", last="Quliyeva", role=kassir_role,
                         phone="+994503002233")
        self.staff_user(shop, branch, username="orxan.anbar", first="Orxan", last="Vəliyev", role=anbardar_role,
                         phone="+994704003344")
        self.staff_user(shop, branch, username="nermin.staj", first="Nərmin", last="Abbasova", role=stajci_role,
                         phone="+994515004455")
        self.staff_user(shop, branch, username="vasif.usta", first="Vasif", last="Tağıyev", role=usta_role,
                         phone="+994556005566", status=User.Status.INVITED)
        self.staff_user(shop, branch, username="kamran.usta", first="Kamran", last="Nəbiyev", role=usta_role,
                         phone="+994707006677", status=User.Status.DISABLED)

        names = [
            ("Rəşad Məmmədov", "+994551234567", "Daimi müştəri."),
            ("Leman Bəşirova", "+994502345678", ""),
            ("Kamran Əliyev", "+994703456789", ""),
            ("Nigar Həsənova", "+994554567890", "Zəng etməzdən əvvəl mesaj yazın."),
            ("Tural Quliyev", "+994515678901", ""),
            ("Aygün Səfərova", "+994506789012", ""),
            ("Elçin Rzayev", "+994777890123", ""),
            ("Səbinə İsmayılova", "+994558901234", "İş yerinə yaxın gəlir, axşam götürür."),
        ]
        c = [Customer.objects.create(shop=shop, full_name=n, phone=p, note=note) for n, p, note in names]
        for cust, days in zip(c, (30, 26, 22, 18, 25, 12, 5, 6)):
            Customer.objects.filter(pk=cust.pk).update(created_at=ago(days=days))

        # --- anbar (yekun qalıq + təmirdə sərf olunan miqdar qədər ilkin giriş)
        scr17 = self.product(shop, "iPhone 17 Pro ekranı", "Apple", "Ekran", "SCR-IP17P", 6, 270, 340, shared=True,
                             mp_price=320)
        bat15 = self.product(shop, "iPhone 15 batareyası", "Apple", "Batareya", "BAT-IP15", 9, 28, 60, min_alert=3,
                             shared=True, mp_price=50)
        scrs24 = self.product(shop, "Samsung S24 ekranı", "Samsung", "Ekran", "SCR-S24", 4, 190, 260)
        usbrn = self.product(shop, "Redmi Note 13 şarj yuvası", "Xiaomi", "Şarj yuvası", "CHG-RN13", 2, 6, 20,
                             min_alert=3)
        cama54 = self.product(shop, "Samsung A54 kamera modulu", "Samsung", "Kamera", "CAM-A54", 3, 32, 60)
        self.product(shop, "Yapışdırıcı lent (universal)", "", "Aksesuar", "ADH-UNI", 20, 0.8, 3, min_alert=5)
        self.product(shop, "Type-C kabel", "Anker", "Aksesuar", "ACC-USBC", 15, 2, 8, min_alert=5)
        self.product(shop, "Qoruyucu şüşə 9H", "", "Aksesuar", "GLS-9H", 40, 1, 6, min_alert=10, shared=True,
                     mp_price=4.5)

        # --- təmirlər (received günü, təhvil günü, ödənişlər)
        r1 = self.repair(shop, branch, owner, c[0], brand="Apple", model="iPhone 17 Pro", issue="Ekran dəyişdirilməsi",
                         cost=280, sale=450, status=RepairStatus.IN_PROGRESS, received=ago(days=2),
                         warranty=14, payments=[(300, CARD, ago(days=2))], imei="356938035643809")
        r2 = self.repair(shop, branch, owner, c[1], brand="Apple", model="iPhone 15", issue="Batareya dəyişdirilməsi",
                         cost=60, sale=120, status=RepairStatus.READY, received=ago(days=3),
                         warranty=30, payments=[(50, CASH, ago(days=3))])
        r3 = self.repair(shop, branch, owner, c[2], brand="Samsung", model="Galaxy S24", issue="Ekran dəyişdirilməsi",
                         cost=210, sale=340, status=RepairStatus.DELIVERED, received=ago(days=20),
                         delivered=ago(days=18), warranty=30, payments=[(340, CASH, ago(days=18))],
                         work_done="Orijinal ekran modulu quraşdırıldı.")
        r4 = self.repair(shop, branch, owner, c[3], brand="Xiaomi", model="Redmi Note 13",
                         issue="Şarj yuvasının dəyişdirilməsi",
                         cost=15, sale=50, status=RepairStatus.DELIVERED, received=ago(days=12),
                         delivered=ago(days=10), warranty=14, payments=[(50, CASH, ago(days=10))])
        r5 = self.repair(shop, branch, owner, c[4], brand="Apple", model="iPhone 13",
                         issue="Anakart təmiri (qısa qapanma)",
                         cost=120, sale=260, status=RepairStatus.DELIVERED, received=ago(days=25),
                         delivered=ago(days=22), warranty=14, payments=[(100, CASH, ago(days=22))],
                         debt_due=(timezone.now() - datetime.timedelta(days=5)).date())  # gecikmiş borc
        r6 = self.repair(shop, branch, owner, c[5], brand="Samsung", model="Galaxy A54",
                         issue="Arxa kameranın dəyişdirilməsi",
                         cost=45, sale=110, status=RepairStatus.DELIVERED, received=ago(days=9),
                         delivered=ago(days=7), warranty=14, payments=[(110, CARD, ago(days=7))])
        self.repair(shop, branch, owner, c[6], brand="Huawei", model="P30", issue="Ekran dəyişdirilməsi",
                    cost=70, sale=150, status=RepairStatus.DIAGNOSING, received=ago(days=1))
        r8 = self.repair(shop, branch, owner, c[7], brand="Apple", model="iPad 9", issue="Şüşənin dəyişdirilməsi",
                         cost=90, sale=200, status=RepairStatus.WAITING_REPAIR, received=ago(days=4),
                         payments=[(50, CASH, ago(days=4))])
        self.repair(shop, branch, owner, c[0], brand="Apple", model="iPhone 12", issue="Dinamikin dəyişdirilməsi",
                    cost=25, sale=80, status=RepairStatus.DELIVERED, received=ago(days=30), delivered=ago(days=28),
                    warranty=30, payments=[(80, CASH, ago(days=28))])  # zəmanət 2 gün qalır
        self.repair(shop, branch, owner, c[2], brand="Samsung", model="Galaxy A14",
                    issue="Proqram təminatı yenilənməsi",
                    cost=0, sale=30, status=RepairStatus.DELIVERED, received=ago(days=6), delivered=ago(days=6),
                    warranty=7, payments=[(30, CASH, ago(days=6))])
        self.repair(shop, branch, owner, c[3], brand="Apple", model="iPhone 14", issue="Ekran dəyişdirilməsi",
                    cost=250, sale=400, status=RepairStatus.DELIVERED, received=ago(days=15), delivered=ago(days=13),
                    warranty=30, payments=[(200, CASH, ago(days=13))],
                    debt_due=(timezone.now() + datetime.timedelta(days=6)).date())  # vaxtı çatmamış borc
        self.repair(shop, branch, owner, c[6], brand="Xiaomi", model="12",
                    issue="Təmirdən imtina (qiymət uyğun gəlmədi)",
                    cost=0, sale=100, status=RepairStatus.CANCELLED, received=ago(days=8))

        # --- təmirdə istifadə olunan hissələr (anbardan avtomatik düşür)
        self.use_part(r1, scr17);
        self.use_part(r2, bat15);
        self.use_part(r3, scrs24)
        self.use_part(r4, usbrn);
        self.use_part(r6, cama54)

        # --- təchizatçılar və borclar
        abc = Supplier.objects.create(shop=shop, name="ABC Parts", phone="+994501112200", note="Apple hissələri")
        idoctor = Supplier.objects.create(shop=shop, name="iDoctor Parts", phone="+994553334455")
        gsm = Supplier.objects.create(shop=shop, name="GSM Aksesuar", phone="+994704445566")
        purchases = [
            (abc, "iPhone 17 Pro ekranları (5 ədəd)", 1350, 850, 6, None),
            (abc, "iPhone 15 batareyaları (10 ədəd)", 280, 280, 20, None),
            (idoctor, "Samsung ekranları (4 ədəd)", 780, 300, 12, None),
            (idoctor, "iPad 9 şüşəsi", 90, 0, 4, r8),
            (gsm, "Kabellər və qoruyucu şüşələr", 190, 190, 25, None),
        ]
        for sup, desc, amount, paid, days, repair in purchases:
            when = ago(days=days)
            p = SupplierPurchase.objects.create(
                shop=shop, supplier=sup, description=desc, amount=amount, paid_amount=paid,
                purchased_at=when.date(), repair=repair,
            )
            if paid:
                CashTransaction.objects.create(
                    shop=shop, branch=branch, type=TransactionType.SUPPLIER_PAYMENT, amount=paid, method=BANK,
                    description=f"{sup.name} — borc ödənişi", supplier=sup, created_by=owner, created_at=when,
                )

        # --- xərclər və kassa
        CashboxOpeningBalance.objects.create(shop=shop, branch=branch, amount=2500, as_of_date=(ago(days=30)).date())
        for cat, desc, amount, method, days in [
            ("İcarə", "Aylıq icarə haqqı", 350, BANK, 24),
            ("Kommunal", "Elektrik hesabı", 45, CASH, 15),
            ("Kommunal", "İnternet", 25, CARD, 14),
            ("Maaş", "Usta maaşı", 250, BANK, 10),
            ("Marketinq", "Instagram reklamı", 60, CARD, 8),
            ("Təsərrüfat", "Təmizlik və çay-şəkər", 18, CASH, 3),
        ]:
            CashTransaction.objects.create(
                shop=shop, branch=branch, type=TransactionType.EXPENSE, amount=amount, method=method,
                description=desc, expense_category=cat, created_by=owner, created_at=ago(days=days),
            )

    # ------------------------------------------------------- MobilTəmir Gəncə
    def seed_gence(self, shop, branch, owner):
        usta_role = self.ensure_role(shop, "Usta", allowed=set(Module.values) - {Module.SETTINGS, Module.USERS})
        kassir_role = self.ensure_role(shop, "Kassir", allowed={Module.CASHBOX, Module.EXPENSES, Module.DEBTS, Module.CUSTOMERS})
        self.staff_user(shop, branch, username="turan.usta", first="Turan", last="Nəzərli", role=usta_role,
                         phone="+994557008899")
        self.staff_user(shop, branch, username="sevinc.kassir", first="Sevinc", last="Qarayeva", role=kassir_role,
                         phone="+994508009900")

        c1 = Customer.objects.create(shop=shop, full_name="Ramin Nəsirov", phone="+994552001122")
        c2 = Customer.objects.create(shop=shop, full_name="Günay Abbasova", phone="+994702003344")
        self.repair(shop, branch, owner, c1, brand="Apple", model="iPhone 14", issue="Ekran dəyişdirilməsi",
                    cost=210, sale=330, status=RepairStatus.DELIVERED, received=ago(days=9), delivered=ago(days=8),
                    warranty=30, payments=[(330, CARD, ago(days=8))])
        self.repair(shop, branch, owner, c2, brand="Samsung", model="Galaxy A34", issue="Batareya dəyişdirilməsi",
                    cost=30, sale=70, status=RepairStatus.IN_PROGRESS, received=ago(days=1),
                    payments=[(30, CASH, ago(days=1))])
        self.product(shop, "Samsung S25 Ultra batareyası", "Samsung", "Batareya", "BAT-S25U", 12, 35, 55, shared=True,
                     mp_price=48)
        self.product(shop, "iPhone 14 ekranı", "Apple", "Ekran", "SCR-IP14", 4, 210, 290, shared=True, mp_price=270)
        self.product(shop, "Xiaomi 13 ekranı", "Xiaomi", "Ekran", "SCR-X13", 6, 95, 150, shared=True, mp_price=135)
        self.product(shop, "Şarj adapteri 20W", "", "Aksesuar", "ACC-20W", 25, 6, 15, min_alert=5, shared=True,
                     mp_price=12)
        CashboxOpeningBalance.objects.create(shop=shop, branch=branch, amount=800, as_of_date=ago(days=30).date())

    # -------------------------------------------------- kiçik mağazalar (sınaq/gecikmiş)
    def seed_small_shop(self, shop, branch, owner, *, prefix):
        usta_role = self.ensure_role(shop, "Usta", allowed=set(Module.values) - {Module.SETTINGS, Module.USERS})
        self.staff_user(shop, branch, username=f"{prefix}.usta", first="Fərid", last="Cəfərov", role=usta_role,
                         phone="+994551112200")
        c1 = Customer.objects.create(shop=shop, full_name="Anar Quliyev", phone="+994557001100")
        c2 = Customer.objects.create(shop=shop, full_name="Lalə Məmmədova", phone="+994708002200")
        self.repair(shop, branch, owner, c1, brand="Samsung", model="Galaxy A15", issue="Ekran dəyişdirilməsi",
                    cost=95, sale=160, status=RepairStatus.IN_PROGRESS, received=ago(days=1))
        self.repair(shop, branch, owner, c2, brand="Apple", model="iPhone 11", issue="Batareya dəyişdirilməsi",
                    cost=35, sale=75, status=RepairStatus.DELIVERED, received=ago(days=5), delivered=ago(days=4),
                    warranty=14, payments=[(75, CASH, ago(days=4))])
        self.product(shop, "Universal batareya dəsti", "", "Batareya", f"BAT-{prefix.upper()}", 6, 20, 40)
        CashboxOpeningBalance.objects.create(shop=shop, branch=branch, amount=200, as_of_date=ago(days=20).date())

    # ------------------------------------------------------------ marketplace
    def seed_marketplace(self, shop1, branch1, owner1, shop2, branch2, owner2):
        def order(buyer, bbranch, buyer_user, seller, sku, qty, note, days, method=BANK):
            product = Product.objects.get(shop=seller, sku=sku)
            o = MarketplaceOrder.objects.create(
                buyer_shop=buyer, buyer_branch=bbranch, requested_by=buyer_user, seller_shop=seller,
                product=product, quantity=qty, unit_price=product.effective_marketplace_price,
                payment_method=method, buyer_note=note,
            )
            MarketplaceOrder.objects.filter(pk=o.pk).update(created_at=ago(days=days))
            o.refresh_from_db()
            return o

        # TechFix (Bakı) Gəncədən alır
        order(shop1, branch1, owner1, shop2, "SCR-X13", 1, "Təcili lazımdır, sabaha qədər", 0)  # gözləyir
        o = order(shop1, branch1, owner1, shop2, "BAT-S25U", 2, "", 10)  # tamamlanıb
        o.accept();
        o.mark_paid();
        o.mark_shipped();
        o.mark_completed()
        o = order(shop1, branch1, owner1, shop2, "SCR-IP14", 1, "", 3)  # yolda
        o.accept();
        o.mark_paid();
        o.mark_shipped()
        # Gəncə (satıcı = TechFix) — Elvin qəbul etməlidir
        order(shop2, branch2, owner2, shop1, "BAT-IP15", 2, "Həftəsonuna qədər lazımdır", 1)  # gözləyir
        o = order(shop2, branch2, owner2, shop1, "GLS-9H", 10, "", 2)
        o.accept()  # ödəniş gözləyir

    # --------------------------------------------------------------- platform
    def seed_platform(self, shop1, shop2, shop3, shop4, plan):
        today = timezone.now().date()
        for shop in (shop1, shop2, shop4):
            for months_back in (2, 1):
                start = (today.replace(day=1) - datetime.timedelta(days=30 * (months_back - 1))).replace(day=1)
                end = start + datetime.timedelta(days=29)
                SubscriptionPayment.objects.create(
                    shop=shop, amount=plan.price_monthly,
                    paid_at=timezone.now() - datetime.timedelta(days=30 * months_back),
                    period_start=start, period_end=end,
                )
        SupportTicket.objects.create(shop=shop1, subject="Qəbz çapında ünvan görünmür",
                                     message="Parametrlərdə ünvanı yazmışam, amma qəbzdə çıxmır.",
                                     status=SupportTicket.Status.OPEN)
        SupportTicket.objects.create(shop=shop2, subject="Yeni filial əlavə etmək istəyirəm",
                                     message="Şəki üçün ikinci filial açmaq olar?",
                                     status=SupportTicket.Status.IN_PROGRESS)
        SupportTicket.objects.create(shop=shop1, subject="Şifrəni unutmuşam", message="Usta üçün şifrə sıfırlandı.",
                                     status=SupportTicket.Status.CLOSED)
        SupportTicket.objects.create(shop=shop3, subject="Planı necə yüksəldə bilərəm?",
                                     message="Sınaq müddəti bitir, Pro plana keçmək istəyirəm.",
                                     status=SupportTicket.Status.OPEN)
        SupportTicket.objects.create(shop=shop4, subject="Ödəniş kartım bloklanıb",
                                     message="Yeni kartla ödənişi necə edim?",
                                     status=SupportTicket.Status.IN_PROGRESS)