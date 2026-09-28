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
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.mixins import IsPlatformAdmin


@dataclass
class Resource:
    key: str
    model_label: str
    label: str
    group: str
    columns: list
    extra_kwargs: dict = field(default_factory=dict)
    exclude: tuple = ()
    _model: Optional[type] = None

    @property
    def model(self):
        if self._model is None:
            self._model = apps.get_model(self.model_label)
        return self._model


PLATFORM = "Platforma"
SERVICE = "Servis məlumatları"

RESOURCES = [
    Resource("shops", "tenants.Shop", "Mağazalar", PLATFORM,
             ["name", "code", "owner_full_name", "city", "plan", "status", "next_payment_at"],
             extra_kwargs={"code": {"required": False, "allow_blank": True}}),
    Resource("plans", "tenants.Plan", "Planlar", PLATFORM,
             ["name", "price_monthly", "max_branches", "max_users"]),
    Resource("branches", "tenants.Branch", "Filiallar", PLATFORM,
             ["name", "shop", "phone", "is_main"]),
    Resource("users", "accounts.User", "İstifadəçilər", PLATFORM,
             ["username", "first_name", "last_name", "shop", "role", "status", "is_platform_admin"],
             exclude=("groups", "user_permissions")),  # password: write-only, hash-lənir
    Resource("roles", "accounts.Role", "Rollar", PLATFORM,
             ["name", "shop", "is_owner_role"]),
    Resource("role-permissions", "accounts.RolePermission", "Rol icazələri", PLATFORM,
             ["role", "module", "is_allowed"]),
    Resource("tickets", "platform_admin.SupportTicket", "Dəstək sorğuları", PLATFORM,
             ["subject", "shop", "status", "created_at"]),
    Resource("payments", "platform_admin.SubscriptionPayment", "Abunə ödənişləri", PLATFORM,
             ["shop", "amount", "period_start", "period_end", "paid_at"]),

    Resource("customers", "customers.Customer", "Müştərilər", SERVICE,
             ["full_name", "phone", "shop", "created_at"]),
    Resource("repairs", "repairs.RepairOrder", "Təmir sifarişləri", SERVICE,
             ["number", "shop", "customer", "device_brand", "device_model", "status", "payment_status", "sale_price"]),
    Resource("repair-payments", "repairs.RepairPayment", "Təmir ödənişləri", SERVICE,
             ["repair", "amount", "method", "paid_at"]),
    Resource("products", "inventory.Product", "Anbar məhsulları", SERVICE,
             ["name", "brand", "shop", "quantity_in_stock", "unit_sale_price", "is_shared_to_marketplace"]),
    Resource("stock-movements", "inventory.StockMovement", "Anbar hərəkətləri", SERVICE,
             ["shop", "product", "movement_type", "quantity_delta", "created_at"]),
    Resource("repair-parts", "inventory.RepairPartUsage", "Təmirdə işlənən hissələr", SERVICE,
             ["repair", "product", "quantity", "unit_cost_at_use"]),
    Resource("suppliers", "suppliers.Supplier", "Təchizatçılar", SERVICE,
             ["name", "phone", "shop"]),
    Resource("supplier-purchases", "suppliers.SupplierPurchase", "Təchizatçı alışları", SERVICE,
             ["shop", "supplier", "description", "amount", "paid_amount", "purchased_at"]),
    Resource("cash-transactions", "finance.CashTransaction", "Kassa əməliyyatları", SERVICE,
             ["shop", "type", "amount", "method", "description", "created_at"]),
    Resource("cash-opening-balances", "finance.CashboxOpeningBalance", "Kassa açılış qalıqları", SERVICE,
             ["shop", "branch", "amount", "as_of_date"]),
    Resource("marketplace-orders", "marketplace.MarketplaceOrder", "Marketplace sifarişləri", SERVICE,
             ["buyer_shop", "seller_shop", "product", "quantity", "unit_price", "status", "created_at"]),
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
    "is_platform_admin": "Platforma admini", "is_superuser": "Superuser", "is_staff": "Admin panelə giriş",
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
        permission_classes = [IsAuthenticated, IsPlatformAdmin]
        filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
        filterset_fields = filter_fields
        ordering_fields = "__all__"

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
    fields = []
    for name, f in ser.fields.items():
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
        "key": res.key, "label": res.label, "group": res.group,
        "columns": res.columns, "filters": filters_meta[:3],
        "searchable": True, "fields": fields,
    }
