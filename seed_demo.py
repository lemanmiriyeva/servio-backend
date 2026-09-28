"""
İşlətmək üçün: python manage.py seed_demo   (köhnə/pozuq məlumat üçün: python manage.py seed_demo --reset)
Dizayndakı nümunə ilə eyni: TechFix Servis, Elvin Hüseynov.
"""
import datetime
from django.utils import timezone
from tenants.models import Plan, Shop, Branch
from accounts.models import User, Role, RolePermission, Module
from customers.models import Customer
from repairs.models import RepairOrder, RepairPayment, RepairStatus, PaymentStatus
from suppliers.models import Supplier, SupplierPurchase
from finance.models import CashTransaction, TransactionType, PaymentMethod

pro, _ = Plan.objects.get_or_create(name="Pro", defaults=dict(price_monthly=49, max_branches=5, max_users=15))

shop, created = Shop.objects.get_or_create(
    code="techfix",
    defaults=dict(
        name="TechFix Servis",
        owner_full_name="Elvin Hüseynov",
        owner_phone="+994501112233",
        city="Bakı",
        plan=pro,
        status=Shop.Status.ACTIVE,
        default_warranty_days=14,
    ),
)

branch, _ = Branch.objects.get_or_create(shop=shop, name="Nəsimi filialı", defaults=dict(is_main=True))

owner_role, _ = Role.objects.get_or_create(shop=shop, name="Admin / Sahib", defaults=dict(is_owner_role=True))
usta_role, _ = Role.objects.get_or_create(shop=shop, name="Usta")
for m in Module.values:
    RolePermission.objects.get_or_create(role=usta_role, module=m, defaults=dict(is_allowed=True))

stajci_role, _ = Role.objects.get_or_create(shop=shop, name="tələbə (stajçı)")
allowed_for_stajci = {Module.REPAIRS, Module.CUSTOMERS, Module.INVENTORY}
for m in Module.values:
    RolePermission.objects.get_or_create(role=stajci_role, module=m, defaults=dict(is_allowed=m in allowed_for_stajci))

if not User.objects.filter(username="elvin.techfix").exists():
    owner = User.objects.create_user(
        username="elvin.techfix", password="parol123", email="elvin@techfix.az",
        first_name="Elvin", last_name="Hüseynov",
        shop=shop, branch=branch, role=owner_role, phone="+994501112233",
    )
else:
    owner = User.objects.get(username="elvin.techfix")

customer, _ = Customer.objects.get_or_create(
    shop=shop, full_name="Rəşad Məmmədov", defaults=dict(phone="+994551234567", note="Daimi müştəri.")
)

repair, created = RepairOrder.objects.get_or_create(
    shop=shop, branch=branch, customer=customer,
    device_brand="Apple", device_model="iPhone 17 Pro",
    defaults=dict(
        issue_description="Ekran dəyişdirilməsi",
        cost_price=280, sale_price=450,
        status=RepairStatus.IN_PROGRESS,
        payment_status=PaymentStatus.PARTIAL,
        debt_due_date=timezone.now().date() + datetime.timedelta(days=9),
        warranty_days=14,
        created_by=owner,
    ),
)
if created:
    RepairPayment.objects.create(repair=repair, amount=300, method=PaymentMethod.CARD, received_by=owner)
    CashTransaction.objects.create(
        shop=shop, branch=branch, type=TransactionType.INCOME, amount=300,
        method=PaymentMethod.CARD, description=f"{repair.number}, {customer.full_name} (qismən)",
        repair=repair, created_by=owner,
    )

supplier, _ = Supplier.objects.get_or_create(shop=shop, name="ABC Parts", defaults=dict(phone="+994501112200"))
SupplierPurchase.objects.get_or_create(
    shop=shop, supplier=supplier, description="iPhone 17 Pro ekranları (5 ədəd)",
    defaults=dict(amount=2200, paid_amount=1400),
)

# --- Anbar + ikinci mağaza (marketplace ssenarisi üçün) ---
from inventory.models import Product, StockMovement, MovementType
from marketplace.models import MarketplaceOrder

techfix_screen, created = Product.objects.get_or_create(
    shop=shop, name="iPhone 17 Pro ekranı", defaults=dict(
        brand="Apple", category="Ekran", sku="SCR-IP17P",
        unit_cost=270, unit_sale_price=340, min_stock_alert=2,
    ),
)
if created:
    StockMovement.objects.create(shop=shop, product=techfix_screen, movement_type=MovementType.PURCHASE_IN,
                                  quantity_delta=5, note="İlkin anbar doldurulması")

# İkinci mağaza — MobilTəmir Gəncə
shop2, _ = Shop.objects.get_or_create(
    code="mobiltemir-gence",
    defaults=dict(name="MobilTəmir Gəncə", owner_full_name="Vüqar Hacıyev", city="Gəncə",
                   plan=pro, status=Shop.Status.ACTIVE),
)
branch2, _ = Branch.objects.get_or_create(shop=shop2, name="Mərkəz filialı", defaults=dict(is_main=True))
owner2_role, _ = Role.objects.get_or_create(shop=shop2, name="Admin / Sahib", defaults=dict(is_owner_role=True))
if not User.objects.filter(username="vuqar.mobiltemir").exists():
    owner2 = User.objects.create_user(
        username="vuqar.mobiltemir", password="parol123",
        first_name="Vüqar", last_name="Hacıyev", shop=shop2, branch=branch2, role=owner2_role,
    )
else:
    owner2 = User.objects.get(username="vuqar.mobiltemir")

# Vüqarın anbarında batareya var və o, marketplace-ə açıqdır
gence_battery, created = Product.objects.get_or_create(
    shop=shop2, name="Samsung S25 Ultra batareyası", defaults=dict(
        brand="Samsung", category="Batareya", sku="BAT-S25U",
        unit_cost=35, unit_sale_price=55, is_shared_to_marketplace=True, marketplace_price=48,
    ),
)
if created:
    StockMovement.objects.create(shop=shop2, product=gence_battery, movement_type=MovementType.PURCHASE_IN,
                                  quantity_delta=12, note="İlkin anbar doldurulması")

# TechFix-in ustası bu batareyanı Gəncədən sifariş edir (nümunə axını)
mp_order, created = MarketplaceOrder.objects.get_or_create(
    buyer_shop=shop, seller_shop=shop2, product=gence_battery,
    defaults=dict(buyer_branch=branch, requested_by=owner, quantity=2,
                  unit_price=gence_battery.effective_marketplace_price,
                  buyer_note="Təcili lazımdır, sabaha qədər"),
)

print("Demo data hazırdır.")
print("Mağaza 1: elvin.techfix / parol123  (TechFix Servis, Bakı)")
print("Mağaza 2: vuqar.mobiltemir / parol123  (MobilTəmir Gəncə)")
print(f"Marketplace nümunə sifariş: #{mp_order.pk} — status: {mp_order.status}")