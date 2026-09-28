from django.contrib.auth.models import AbstractUser
from django.db import models
from tenants.models import Shop, Branch


class Module(models.TextChoices):
    """Dizayndakı 'Rol icazələri' cədvəlindəki hər sətir bir modula uyğundur."""
    REPAIRS = "repairs", "Təmir / Xidmətlər"
    CUSTOMERS = "customers", "Müştərilər"
    INVENTORY = "inventory", "Anbar"
    MARKETPLACE = "marketplace", "Marketplace (mağazalararası bazar)"
    SUPPLIERS = "suppliers", "Təchizatçılar"
    CASHBOX = "cashbox", "Kassa — bütün əməliyyatlar"
    EXPENSES = "expenses", "Xərclər"
    DEBTS = "debts", "Borclar — ümumi məbləğ"
    REPORTS = "reports", "Hesabatlar / Analitika"
    USERS = "users", "İstifadəçilər və icazələr"
    SETTINGS = "settings", "Parametrlər"
    REVENUE_NUMBERS = "revenue_numbers", "Gəlir / net mənfəət rəqəmləri"


# Yeni rol yaradılanda defolt açıq olan bölmələr (mağaza sahibi sonra "Rollar və icazələr"də dəyişə bilər).
# Maliyyə/idarəetmə bölmələri (kassa, xərclər, borclar, hesabat, istifadəçilər, parametrlər, gəlir rəqəmləri) defolt bağlıdır.
DEFAULT_ROLE_MODULES = {
    Module.REPAIRS, Module.CUSTOMERS, Module.INVENTORY, Module.MARKETPLACE, Module.SUPPLIERS,
}


class Role(models.Model):
    """Hər mağaza öz rollarını qura bilər (default: Admin/Sahib, Usta, tələbə)."""
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="roles")
    name = models.CharField(max_length=80)
    is_owner_role = models.BooleanField(default=False, help_text="Sahib rolu — həmişə hər şeyə icazəlidir")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["shop", "name"], name="unique_role_name_per_shop")
        ]

    def __str__(self):
        return f"{self.name} ({self.shop.name})"

    def has_permission(self, module: str) -> bool:
        if self.is_owner_role:
            return True
        return self.permissions.filter(module=module, is_allowed=True).exists()


class RolePermission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="permissions")
    module = models.CharField(max_length=32, choices=Module.choices)
    is_allowed = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["role", "module"], name="unique_permission_per_role_module")
        ]

    def __str__(self):
        return f"{self.role} · {self.get_module_display()} · {'Açıq' if self.is_allowed else 'Bağlı'}"


class User(AbstractUser):
    """
    Platform Super Admin: shop=None, is_platform_admin=True
    Mağaza istifadəçisi: shop dolu, role dolu
    """
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, null=True, blank=True, related_name="users")
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="users")
    role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True, blank=True, related_name="users")
    phone = models.CharField(max_length=32, blank=True)
    is_platform_admin = models.BooleanField(default=False)

    class Status(models.TextChoices):
        ACTIVE = "active", "Aktiv"
        INVITED = "invited", "Dəvət gözləyir"
        DISABLED = "disabled", "Deaktiv"

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    @property
    def initials(self) -> str:
        parts = [p for p in [self.first_name, self.last_name] if p]
        return "".join(p[0] for p in parts[:2]).upper() or (self.username[:2].upper() if self.username else "??")

    def has_module_permission(self, module: str) -> bool:
        if self.is_superuser or self.is_platform_admin:
            return True
        if self.role_id:
            return self.role.has_permission(module)
        return False

    def __str__(self):
        return self.get_full_name() or self.username
