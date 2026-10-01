from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # Django-nun daxili admin paneli — kənardan hücumların qarşısını almaq üçün
    # standart "/admin/" əvəzinə gizli "/kapitan/" ünvanında (bot/skan cəhdləri "/admin/"-ə düşür).
    path("kapitan/", admin.site.urls),

    # Auth + istifadəçilər/rollar
    path("api/", include("accounts.urls")),

    # Tenant-scoped mağaza modulları
    path("api/customers/", include("customers.urls")),
    path("api/repairs/", include("repairs.urls")),
    path("api/inventory/", include("inventory.urls")),
    path("api/suppliers/", include("suppliers.urls")),
    path("api/cashbox/", include("finance.urls")),
    path("api/marketplace/", include("marketplace.urls")),
    path("api/", include("reports.urls")),           # /api/dashboard/, /api/reports/summary/
    path("api/", include("tenants.urls")),           # /api/my-shop/, /api/branches/, /api/shops/ (Super Admin), /api/plans/
    path("api/", include("sitecontent.urls")),       # /api/site-content/ — açıq, ictimai sayt üçün

    # Platform Super Admin (əlavə, platform/ prefiksli görünüş üçün)
    path("api/platform/", include("platform_admin.urls")),  # /api/platform/tickets/, /api/platform/dashboard/
]