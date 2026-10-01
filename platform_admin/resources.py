"""
Platforma (Super Admin) üçün generik CRUD.

Django admin-də olan HƏR modelin platforma panelində də idarə olunması üçün bir yerdə qeydiyyat.
Hər resurs üçün avtomatik yaradılır:
  - DRF serializer (FK-lar üçün oxunaqlı `<sahə>_display` ilə)
  - ModelViewSet (axtarış, filtr, sıralama, səhifələmə) — yalnız Platform Super Admin
  - meta (sahələr, tiplər, seçimlər, əlaqəli resurs) — frontend formu buna görə çəkilir
"""
from dataclasses import dataclass, field
from typing import Optional

import enum
from decimal import Decimal

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.db import IntegrityError, models
from django.db.models import ProtectedError, RestrictedError
from django.utils.crypto import get_random_string
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, serializers, status, viewsets
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.response import Response


@dataclass
class Resource:
    key: str
    model_label: str
    label: str
    group: str
    columns: list
    extra_kwargs: dict = field(default_factory=dict)
    exclude: tuple = ()
    section: str = ""     # sidebar-da QRUPUN özü hansı üst bölmənin altında görünür (bax: SEC_*)
    hidden: bool = False  # True olsa, sidebar-da AYRI bağlantı kimi göstərilmir (yalnız mağaza
                           # kartının "Ətraflı" səhifəsində tab kimi, ya da başqa UI-dan çağırılır) —
                           # amma API (/api/platform/r/<key>/) hər zaman işləyir.
    shop_scoped: bool = False  # True olsa: (1) mağaza SAHİBİ rolu olan istifadəçi də bu resursa
                                # /api/platform/r/<key>/ ilə daxil ola bilər, AMMA yalnız ÖZ
                                # mağazasının qeydlərini görür/yaradır/redaktə edir (serverdə məcburi
                                # `shop=request.user.shop` tətbiq olunur, client-in göndərdiyi `shop`
                                # dəyəri nəzərə alınmır). Platform Super Admin isə həmişə hamısını görür.
    _model: Optional[type] = None

    @property
    def model(self):
        if self._model is None:
            self._model = apps.get_model(self.model_label)
        return self._model


# ----------------------------------------------------------------------------
# Üst bölmələr (SEC_*) — sidebar-da bir-birindən vizual olaraq AYRILMIŞ 4 böyük blok.
# Müştərinin tələbi: "Servis məlumatları" adlı qarışıq, bütün mağazaların datasının bir yerdə
# göründüyü bölmə olmasın; əvəzinə hər mağazanın öz məlumatı "Mağazalar" bölməsindən o mağazaya
# daxil olanda görünsün. Sayt məzmunu (marketinq saytı) və Planlar/Abunələr isə ayrı-ayrı,
# aydın bölmələr kimi dursun.
SEC_SHOPS = "Mağazalar"
SEC_PLATFORM = "Platforma"
SEC_PLANS = "Planlar və Abunələr"
SEC_SITE = "Sayt məzmunu"

# Qrup (sub-başlıq) — hər SEC_* bölməsinin daxilində sidebar-da görünən kiçik başlıqlar.
PLATFORM = "Platforma"
SHOPS_GROUP = "Mağazalar"
PLANS_GROUP = "Planlar və abunə ödənişləri"
# İctimai (marketinq) saytın hər bölməsi üçün AYRI qrup — sidebar-da saytdakı səhifələrlə
# bir-birinə birbaşa uyğun gəlsin deyə (əvvəllər hamısı tək "İctimai sayt" qrupunda idi,
# qarışıq görünürdü). Hər qrup elə həmin adda açılan sayt səhifəsinə aiddir.
SITE_HOME = "Sayt: Ana səhifə"
SITE_FEATURES = "Sayt: Funksiyalar"
SITE_ABOUT = "Sayt: Haqqımızda"
SITE_FAQ = "Sayt: FAQ"
SITE_CONTACT = "Sayt: Əlaqə"
SITE_GENERAL = "Sayt: Loqo və marka"

# Bir mağazanın "Ətraflı" (drill-down) səhifəsində tab kimi göstərilən, həmin mağazaya aid
# resurslar. Bunlar sidebar-da AYRI bağlantı kimi görünmür (hidden=True) — çünki hamısı eyni
# `shop` FK-sına malikdir və bir mağazanın içinə girəndə avtomatik `?shop=<id>` ilə filtrlənərək
# açılır (bax: frontend `/platform/shops/[id]`). API-ları yenə işləkdir, sadəcə əsas sidebar-da
# bütün mağazaların datası bir yerdə qarışıq göstərilmir.
RESOURCES = [
    Resource("shops", "tenants.Shop", "Mağazalar", SHOPS_GROUP,
             ["name", "code", "owner_full_name", "city", "plan", "status", "next_payment_at",
              "is_active", "disabled_reason"],
             extra_kwargs={"code": {"required": False, "allow_blank": True}},
             section=SEC_SHOPS),

    # -- Mağazaya aid, "Ətraflı" səhifəsində tab kimi açılan resurslar (sidebar-da gizlidir).
    #    `shop_scoped=True` — mağazanın SAHİB (owner) rolu olan istifadəçisi də bunlara
    #    /api/platform/r/<key>/ ilə daxil ola bilər, amma yalnız ÖZ mağazasının qeydlərinə. --
    Resource("branches", "tenants.Branch", "Filiallar", SHOPS_GROUP,
             ["name", "shop", "phone", "is_main"], section=SEC_SHOPS, hidden=True, shop_scoped=True),
    Resource("customers", "customers.Customer", "Müştərilər", SHOPS_GROUP,
             ["full_name", "phone", "shop", "created_at"], section=SEC_SHOPS, hidden=True, shop_scoped=True),
    Resource("repairs", "repairs.RepairOrder", "Təmir sifarişləri", SHOPS_GROUP,
             ["number", "shop", "customer", "device_brand", "device_model", "status", "payment_status", "sale_price"],
             section=SEC_SHOPS, hidden=True, shop_scoped=True),
    Resource("products", "inventory.Product", "Anbar məhsulları", SHOPS_GROUP,
             ["name", "brand", "shop", "quantity_in_stock", "unit_sale_price", "is_shared_to_marketplace"],
             section=SEC_SHOPS, hidden=True, shop_scoped=True),
    Resource("stock-movements", "inventory.StockMovement", "Anbar hərəkətləri", SHOPS_GROUP,
             ["shop", "product", "movement_type", "quantity_delta", "created_at"],
             section=SEC_SHOPS, hidden=True, shop_scoped=True),
    Resource("suppliers", "suppliers.Supplier", "Təchizatçılar", SHOPS_GROUP,
             ["name", "phone", "shop"], section=SEC_SHOPS, hidden=True, shop_scoped=True),
    Resource("supplier-purchases", "suppliers.SupplierPurchase", "Təchizatçı alışları", SHOPS_GROUP,
             ["shop", "supplier", "description", "amount", "paid_amount", "purchased_at"],
             section=SEC_SHOPS, hidden=True, shop_scoped=True),
    Resource("cash-transactions", "finance.CashTransaction", "Kassa əməliyyatları", SHOPS_GROUP,
             ["shop", "type", "amount", "method", "description", "created_at"],
             section=SEC_SHOPS, hidden=True, shop_scoped=True),
    Resource("cash-opening-balances", "finance.CashboxOpeningBalance", "Kassa açılış qalıqları", SHOPS_GROUP,
             ["shop", "branch", "amount", "as_of_date"], section=SEC_SHOPS, hidden=True, shop_scoped=True),

    # -- Platforma: birbaşa bir mağazaya aid olmayan / bir neçə mağazanı əhatə edən qeydlər.
    #    İstifadəçilər və Rollar istisnadır: HƏM burada (bütün mağazalar üzrə, sidebar-da görünən,
    #    yalnız Platform Super Admin üçün) HƏM DƏ hər mağazanın öz "Ətraflı" səhifəsində tab kimi
    #    (yalnız öz mağazasına, `shop_scoped=True` ilə) görünür. --
    Resource("users", "accounts.User", "İstifadəçilər", PLATFORM,
             ["username", "first_name", "last_name", "shop", "role", "status",
              "is_shop_admin", "is_platform_admin"],
             exclude=("groups", "user_permissions"),  # password: write-only, hash-lənir
             section=SEC_PLATFORM, shop_scoped=True),
    Resource("roles", "accounts.Role", "Rollar", PLATFORM,
             ["name", "shop", "is_owner_role"], section=SEC_PLATFORM, shop_scoped=True),
    Resource("role-permissions", "accounts.RolePermission", "Rol icazələri", PLATFORM,
             ["role", "module", "is_allowed"], section=SEC_PLATFORM),
    Resource("tickets", "platform_admin.SupportTicket", "Dəstək sorğuları", PLATFORM,
             ["subject", "shop", "status", "created_at"], section=SEC_PLATFORM),
    Resource("repair-payments", "repairs.RepairPayment", "Təmir ödənişləri", PLATFORM,
             ["repair", "amount", "method", "paid_at"], section=SEC_PLATFORM),
    Resource("repair-parts", "inventory.RepairPartUsage", "Təmirdə işlənən hissələr", PLATFORM,
             ["repair", "product", "quantity", "unit_cost_at_use"], section=SEC_PLATFORM),
    Resource("marketplace-orders", "marketplace.MarketplaceOrder", "Marketplace sifarişləri", PLATFORM,
             ["buyer_shop", "seller_shop", "product", "quantity", "unit_price", "status", "created_at"],
             section=SEC_PLATFORM),

    # -- Planlar və Abunələr: sırf Baş Admin ilə bağlı, mağazaların özünə aid olmayan bölmə --
    Resource("plans", "tenants.Plan", "Planlar", PLANS_GROUP,
             ["name", "price_monthly", "max_branches", "max_users", "is_featured", "show_on_pricing_page"],
             section=SEC_PLANS),
    Resource("payments", "platform_admin.SubscriptionPayment", "Abunə ödənişləri", PLANS_GROUP,
             ["shop", "amount", "period_start", "period_end", "paid_at"], section=SEC_PLANS),

    # İctimai sayt (Ana səhifə / Funksiyalar / Qiymətlər / Haqqımızda / FAQ / Əlaqə) məzmunu.
    # Hər bölmə elə saytdakı həmin səhifənin adını daşıyır ki, admin panelində işləyən adam
    # harada nəyi redaktə edəcəyini kod/model adına baxmadan anlasın. Planlar (yuxarıda) eyni
    # zamanda ictimai Qiymətlər səhifəsini də qidalandırır.

    # -- Ana səhifə: baş yazı (hero) + "necə işləyir" addımları --
    Resource("home-hero", "sitecontent.SiteSettings", "Baş yazı (hero mətni)", SITE_HOME,
             ["hero_title"],
             exclude=("brand_name", "tagline", "logo", "email", "phone", "whatsapp",
                       "address", "hours", "footer_note"),
             section=SEC_SITE),
    Resource("home-steps", "sitecontent.HomeStep", "\"Necə işləyir\" addımları", SITE_HOME,
             ["number", "title", "order", "is_active"], section=SEC_SITE),

    # -- Funksiyalar: Ana səhifə + Funksiyalar səhifəsindəki funksiya kartları --
    Resource("feature-items", "sitecontent.FeatureItem", "Funksiya kartları", SITE_FEATURES,
             ["title", "icon", "tone", "order", "is_active"], section=SEC_SITE),

    # -- Haqqımızda: dəyər kartları --
    Resource("about-values", "sitecontent.AboutValue", "Haqqımızda dəyərləri", SITE_ABOUT,
             ["title", "icon", "order", "is_active"], section=SEC_SITE),

    # -- FAQ: sual-cavablar --
    Resource("faq-items", "sitecontent.FaqItem", "FAQ sualları", SITE_FAQ,
             ["question", "order", "is_active"], section=SEC_SITE),

    # -- Əlaqə: telefon/e-poçt/ünvan/iş saatları (Əlaqə səhifəsi + footer-də görünür) --
    Resource("contact-info", "sitecontent.SiteSettings", "Əlaqə məlumatları", SITE_CONTACT,
             ["email", "phone", "address"],
             exclude=("brand_name", "tagline", "logo", "hero_title", "hero_subtitle", "footer_note"),
             section=SEC_SITE),

    # -- Loqo və marka: bütün səhifələrdə (header/footer) görünən ümumi brendinq --
    Resource("site-branding", "sitecontent.SiteSettings", "Loqo və marka", SITE_GENERAL,
             ["brand_name", "tagline"],
             exclude=("hero_title", "hero_subtitle", "email", "phone", "whatsapp", "address", "hours"),
             section=SEC_SITE),
]

# Mağazanın "Ətraflı" səhifəsində tab kimi göstərilən resurslar — bu sıra ilə, hamısı birbaşa
# `shop` FK-sı ilə filtrlənir. Frontend bu siyahını sərt-kodlanmış saxlayır (sadəcə naviqasiya
# təşkilatıdır, backend-dən ayrıca endpoint tələb etmir — mövcud `/api/platform/r/<key>/?shop=<id>`
# kifayətdir).
SHOP_DETAIL_TABS = [
    ("customers", "Müştərilər"),
    ("repairs", "Təmir sifarişləri"),
    ("products", "Anbar"),
    ("stock-movements", "Anbar hərəkətləri"),
    ("suppliers", "Təchizatçılar"),
    ("supplier-purchases", "Təchizatçı alışları"),
    ("cash-transactions", "Kassa"),
    ("cash-opening-balances", "Kassa açılış qalığı"),
    ("branches", "Filiallar"),
    ("users", "İstifadəçilər"),
    ("roles", "Rollar"),
]

BY_KEY = {r.key: r for r in RESOURCES}


def resource_key_for_model(model) -> Optional[str]:
    for r in RESOURCES:
        if r.model is model:
            return r.key
    return None


FIELD_LABELS = {
    "id": "ID", "name": "Ad", "code": "Kod", "shop": "Mağaza", "branch": "Filial", "role": "Rol", "plan": "Plan",
    "status": "Status", "city": "Şəhər", "phone": "Telefon", "email": "E-poçt", "address": "Ünvan",
    "created_at": "Yaradılıb", "updated_at": "Yenilənib", "note": "Qeyd", "description": "Təsvir",
    "owner_full_name": "Sahibin adı", "owner_phone": "Sahibin telefonu", "owner_email": "Sahibin e-poçtu",
    "logo_initials": "Loqo hərfləri", "work_hours": "İş saatları", "tax_id": "VÖEN",
    "receipt_terms": "Qəbz şərtləri", "trial_ends_at": "Sınaq bitmə tarixi", "next_payment_at": "Növbəti ödəniş",
    "default_warranty_days": "Standart zəmanət (gün)", "currency": "Valyuta", "is_active": "Aktivdir",
    "price_monthly": "Aylıq qiymət", "max_branches": "Maks. filial", "max_users": "Maks. istifadəçi",
    "is_main": "Əsas filial", "is_owner_role": "Sahib rolu", "module": "Modul", "is_allowed": "İcazə verilib",
    "username": "Login", "first_name": "Ad", "last_name": "Soyad", "password": "Şifrə",
    "is_platform_admin": "Platforma Super Admini (BÜTÜN mağazaları görür!)",
    "is_superuser": "Superuser (texniki, Platforma Super Admini ilə eyni təsirə malikdir)",
    "is_staff": "Admin panelə giriş",
    "is_shop_admin": "Mağaza admini (Platforma panelinə — yalnız öz mağazası üçün giriş)",
    "last_login": "Son giriş", "date_joined": "Qoşulub", "last_seen_at": "Son görünmə",
    "subject": "Mövzu", "message": "Mesaj", "amount": "Məbləğ", "paid_at": "Ödəniş tarixi",
    "period_start": "Dövr başlanğıcı", "period_end": "Dövr sonu",
    "full_name": "Ad Soyad", "number": "Nömrə", "customer": "Müştəri", "device_brand": "Cihaz markası",
    "device_model": "Cihaz modeli", "device_imei": "IMEI", "device_serial": "Seriya nömrəsi",
    "accessories_note": "Aksesuarlar", "issue_description": "Problem", "work_done_note": "Görülən iş",
    "cost_price": "Maya dəyəri", "sale_price": "Satış qiyməti", "payment_status": "Ödəniş statusu",
    "debt_due_date": "Borc son tarixi", "warranty_days": "Zəmanət (gün)", "warranty_started_at": "Zəmanət başlanğıcı",
    "received_at": "Qəbul tarixi", "delivered_at": "Təhvil tarixi", "created_by": "Yaradan",
    "repair": "Təmir", "method": "Ödəniş üsulu", "received_by": "Qəbul edən",
    "brand": "Marka", "category": "Kateqoriya", "sku": "SKU", "quantity_in_stock": "Anbarda say",
    "min_stock_alert": "Minimum say xəbərdarlığı", "unit_cost": "Vahid maya", "unit_sale_price": "Vahid satış qiyməti",
    "is_shared_to_marketplace": "Marketplace-də paylaşılır", "marketplace_price": "Marketplace qiyməti",
    "product": "Məhsul", "movement_type": "Hərəkət növü", "quantity_delta": "Say dəyişikliyi",
    "related_repair": "Əlaqəli təmir", "quantity": "Say", "unit_cost_at_use": "İstifadə vaxtı vahid maya",
    "buyer_shop": "Alıcı mağaza", "buyer_branch": "Alıcı filial", "requested_by": "Sorğu verən",
    "seller_shop": "Satıcı mağaza", "unit_price": "Vahid qiymət", "payment_method": "Ödəniş üsulu",
    "buyer_note": "Alıcı qeydi", "seller_note": "Satıcı qeydi", "responded_at": "Cavab tarixi",
    "completed_at": "Tamamlanma tarixi", "type": "Növ", "supplier": "Təchizatçı", "expense_category": "Xərc kateqoriyası",
    "paid_amount": "Ödənilən məbləğ", "purchased_at": "Alış tarixi", "as_of_date": "Tarix",
    "public_description": "İzah (Qiymətlər səhifəsində)", "public_features": "Üstünlüklər (hər sətir — bir bənd)",
    "is_featured": "Ən populyar kimi göstər", "show_on_pricing_page": "Qiymətlər səhifəsində göstər",
    "sort_order": "Sıra", "order": "Sıra", "question": "Sual", "answer": "Cavab",
    "icon": "İkon", "tone": "Rəng tonu", "short_description": "Qısa təsvir", "points": "Bəndlər (hər sətir — bir bənd)",
    "brand_name": "Marka adı", "tagline": "Şüar", "logo": "Loqo", "hero_title": "Baş başlıq (hero)",
    "hero_subtitle": "Alt başlıq (hero)", "whatsapp": "WhatsApp nömrəsi", "footer_note": "Footer qeydi",
    "number": "Nömrə", "text": "Mətn", "updated_at": "Yenilənib",
}


class DisplayField(serializers.Field):
    """Oxunaqlı mətn (str(obj)) — yalnız oxumaq üçün."""

    def __init__(self, **kwargs):
        kwargs["read_only"] = True
        super().__init__(**kwargs)

    def to_representation(self, value):
        return str(value)


class PasswordMixin:
    """User üçün: şifrə write-only, hash-lənərək saxlanır."""

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = self.Meta.model(**validated_data)
        user.set_password(password or get_random_string(12))
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save(update_fields=["password"])
        return user


def _fk_names(model):
    return [f.name for f in model._meta.concrete_fields if f.is_relation]


def build_serializer(res: Resource):
    model = res.model
    attrs = {"display": DisplayField(source="*")}
    for n in _fk_names(model):
        if n in res.exclude:
            continue
        attrs[f"{n}_display"] = DisplayField(source=n)

    meta_attrs = {"model": model, "extra_kwargs": dict(res.extra_kwargs)}
    if res.exclude:
        meta_attrs["exclude"] = res.exclude
    else:
        meta_attrs["fields"] = "__all__"
    attrs["Meta"] = type("Meta", (), meta_attrs)

    bases = (serializers.ModelSerializer,)
    if res.key == "users":
        attrs["password"] = serializers.CharField(write_only=True, required=False, allow_blank=True, min_length=6)
        bases = (PasswordMixin, serializers.ModelSerializer)
    return type(f"{model.__name__}PlatformSerializer", bases, attrs)


def _is_shop_admin(user) -> bool:
    """
    Mağaza admini — `is_shop_admin=True` və bir mağazaya təyin edilib. Bu, Rol sistemindən
    (Sahib/Usta və s.) TAMAM AYRI, sırf Platforma panelinə giriş üçün olan bir bayraqdır:
    "Sahib" rolu mağaza-daxili modul icazələrini idarə edir, `is_shop_admin` isə YALNIZ bu
    istifadəçinin öz mağazası üçün Platforma panelinə (bu modula) girə bilib-bilmədiyini həll edir.
    """
    return bool(user and user.is_authenticated and user.shop_id and user.is_shop_admin)


class IsPlatformAdminOrShopOwner(BasePermission):
    """
    Platform Super Admin — hər resursa, bütün mağazalar üzrə.
    Mağaza admini (`is_shop_admin=True`) — YALNIZ `shop_scoped=True` resurslara, və YALNIZ öz
    mağazasının qeydlərinə (filtrləmə `get_queryset`-də, məcburi `shop` təyini
    `perform_create/update`-də edilir).
    """
    message = "Bu bölməyə giriş icazəniz yoxdur."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_platform_admin or user.is_superuser:
            return True
        res: Resource = getattr(view, "platform_resource", None)
        return bool(res and res.shop_scoped and _is_shop_admin(user))


# Mağaza adminin `accounts.User` resursu üzərindən HEÇ VAXT açıb dəyişə bilmədiyi, imtiyaz
# artırma riski daşıyan sahələr — yaratma/yeniləmə zamanı serverdə məcburi False-a sıfırlanır.
# `is_shop_admin` də buradadır: kim mağaza admini olacağını YALNIZ Platform Super Admin təyin edir.
_PRIVILEGE_FIELDS = ("is_platform_admin", "is_superuser", "is_staff", "is_shop_admin")


def build_viewset(res: Resource):
    model = res.model
    ser = build_serializer(res)
    fks = [n for n in _fk_names(model) if n not in res.exclude]

    qs = model.objects.select_related(*fks).all()
    if not qs.ordered:
        qs = qs.order_by("-pk")

    filter_fields = [
        f.name for f in model._meta.concrete_fields
        if f.name not in res.exclude and (f.is_relation or f.choices or isinstance(f, models.BooleanField))
    ]
    search_fields = [
        f.name for f in model._meta.concrete_fields
        if isinstance(f, (models.CharField, models.TextField)) and not f.is_relation
        and f.name not in ("password",) and f.name not in res.exclude and not f.choices
    ][:8]

    class PlatformViewSet(viewsets.ModelViewSet):
        queryset = qs
        serializer_class = ser
        platform_resource = res
        permission_classes = [IsAuthenticated, IsPlatformAdminOrShopOwner]
        filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
        filterset_fields = filter_fields
        ordering_fields = "__all__"

        def get_queryset(self):
            qs = super().get_queryset()
            user = self.request.user
            if user.is_platform_admin or user.is_superuser:
                return qs
            # Buraya yalnız shop_scoped resurslar üçün, mağaza sahibi kimi çatıla bilər (permission
            # bunu artıq təmin edir) — hər ehtimala qarşı yenidən öz mağazası ilə filtrlənir.
            return qs.filter(shop_id=user.shop_id)

        def _shop_locked_kwargs(self):
            """Mağaza sahibi üçün: `shop` həmişə özününkünə məcburi edilir, imtiyaz sahələri bağlanır."""
            user = self.request.user
            if user.is_platform_admin or user.is_superuser:
                return {}
            extra = {"shop_id": user.shop_id}
            if model is apps.get_model("accounts.User"):
                extra.update({f: False for f in _PRIVILEGE_FIELDS if hasattr(model, f)})
            return extra

        def perform_create(self, serializer):
            instance = serializer.save(**self._shop_locked_kwargs())
            # Abunə ödənişi qeydə alınanda mağaza avtomatik aktivləşir (bağlıdırsa) və
            # növbəti ödəniş tarixi irəli aparılır — Baş Admin ayrıca "aç" düyməsinə
            # basmasın deyə.
            if res.key == "payments" and getattr(instance, "shop_id", None):
                instance.shop.reactivate()

        def perform_update(self, serializer):
            serializer.save(**self._shop_locked_kwargs())

        def handle_exception(self, exc):
            if isinstance(exc, IntegrityError):
                return Response(
                    {"detail": "Bu məlumat saxlanıla bilmədi (təkrarlanan və ya əlaqəli qeyd xətası)."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return super().handle_exception(exc)

        def destroy(self, request, *args, **kwargs):
            obj = self.get_object()
            if model is apps.get_model("accounts.User") and obj.pk == request.user.pk:
                return Response({"detail": "Öz hesabınızı silə bilməzsiniz."}, status=status.HTTP_400_BAD_REQUEST)
            try:
                obj.delete()
            except (ProtectedError, RestrictedError):
                return Response(
                    {"detail": "Bu qeyd başqa məlumatlarla bağlıdır, silinə bilməz."},
                    status=status.HTTP_409_CONFLICT,
                )
            return Response(status=status.HTTP_204_NO_CONTENT)

    PlatformViewSet.search_fields = search_fields
    PlatformViewSet.__name__ = f"{model.__name__}PlatformViewSet"
    return PlatformViewSet


def _field_type(f):
    if isinstance(f, serializers.ImageField):
        return "image"
    if isinstance(f, serializers.PrimaryKeyRelatedField):
        return "related"
    if isinstance(f, serializers.ChoiceField):
        return "choice"
    if isinstance(f, serializers.BooleanField):
        return "boolean"
    if isinstance(f, (serializers.DecimalField, serializers.FloatField)):
        return "decimal"
    if isinstance(f, serializers.IntegerField):
        return "integer"
    if isinstance(f, serializers.DateTimeField):
        return "datetime"
    if isinstance(f, serializers.DateField):
        return "date"
    if isinstance(f, serializers.EmailField):
        return "email"
    if isinstance(f, serializers.CharField):
        return "textarea" if f.style.get("base_template") == "textarea.html" else "text"
    return "text"


def build_meta(res: Resource, request=None):
    ser = build_serializer(res)(context={"request": request})
    user = getattr(request, "user", None)
    # `request=None` (daxili/introspeksiya çağırışı, məs. testlər) — qoruyacaq konkret istifadəçi
    # olmadığı üçün tam sxem qaytarılır. Real HTTP sorğularında `request` HƏMİŞƏ ötürülür
    # (bax: `PlatformResourcesView`), ona görə bu budaq heç vaxt anonim bir API cavabına çıxmır.
    is_admin = request is None or bool(user and (user.is_platform_admin or user.is_superuser))
    fields = []
    for name, f in ser.fields.items():
        # Mağaza sahibi `accounts.User` formunda imtiyaz sahələrini (platforma admini, superuser,
        # admin panelə giriş) heç görməməlidir — nə göstərmək, nə də dəyişməyə cəhd etmək üçün.
        if not is_admin and name in _PRIVILEGE_FIELDS:
            continue
        d = {
            "name": name,
            "label": FIELD_LABELS.get(name) or str(f.label or name),
            "type": _field_type(f),
            "required": bool(f.required) and not f.read_only,
            "read_only": bool(f.read_only),
            "computed": isinstance(f, DisplayField),
            "allow_null": bool(getattr(f, "allow_null", False)),
            "write_only": bool(getattr(f, "write_only", False)),
            "help": str(f.help_text or ""),
        }
        try:
            mf = res.model._meta.get_field(name)
        except FieldDoesNotExist:
            mf = None
        if mf is not None and mf.has_default() and not callable(mf.default):
            dv = mf.default.value if isinstance(mf.default, enum.Enum) else mf.default
            d["default"] = str(dv) if isinstance(dv, Decimal) else dv
        if d["type"] == "choice":
            d["choices"] = [{"value": k, "label": str(v)} for k, v in f.choices.items()]
        if d["type"] == "related":
            d["related"] = resource_key_for_model(f.queryset.model) if f.queryset is not None else None
        fields.append(d)

    filters_meta = []
    for f in res.model._meta.concrete_fields:
        if f.name in res.exclude:
            continue
        if f.is_relation and f.related_model is apps.get_model("tenants.Shop"):
            filters_meta.append(f.name)
        elif f.choices and f.name in ("status", "type", "payment_status", "movement_type"):
            filters_meta.append(f.name)
    return {
        "key": res.key, "label": res.label, "group": res.group, "section": res.section,
        "hidden": res.hidden, "columns": res.columns, "filters": filters_meta[:3],
        "searchable": True, "fields": fields,
    }