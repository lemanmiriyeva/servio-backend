# ServisCRM — Backend (1-ci addım: verilənlər bazası və admin panel)

## Quraşdırma
```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python3 manage.py migrate
python3 manage.py shell < seed_demo.py     # dizayndakı nümunə məlumatları (TechFix Servis)
python3 manage.py shell -c "from accounts.models import User; User.objects.create_superuser('superadmin','admin@serviscrm.az','parol123', is_platform_admin=True)"
python3 manage.py runserver
```
Sonra `http://127.0.0.1:8000/admin/` ünvanına daxil olun:
- Mağaza istifadəçisi: `elvin.techfix` / `parol123`
- Platform (Super Admin): `superadmin` / `parol123`

## Struktur
- `tenants` — Mağaza (Shop), Filial (Branch), Plan
- `accounts` — İstifadəçi (User), Rol (Role), Modul üzrə icazələr (RolePermission)
- `customers` — Müştəri
- `repairs` — Təmir/Xidmət sifarişi (cihaz məlumatı daxil), Zəmanət (hesablanır), Ödəniş
- `inventory` — Öz mağazanın anbarı (Product), hər hərəkət (StockMovement), təmirdə sərf (RepairPartUsage)
- `marketplace` — **Mağazalararası bazar**: bax aşağıda
- `finance` — Kassa əməliyyatları (gəlir/xərc/təchizatçı ödənişi)
- `suppliers` — Təchizatçı və alışlar (borc avtomatik hesablanır)
- `platform_admin` — Super Admin üçün dəstək sorğuları və abunə ödənişləri

## Marketplace (mağazalararası bazar) — necə işləyir
1. Bir mağaza öz anbarındakı məhsulu `is_shared_to_marketplace=True` edir və `marketplace_price` təyin edir.
2. Başqa mağazanın ustası API üzərindən (növbəti addımda ediləcək) bütün mağazalar üzrə
   **yalnız paylaşıma açıq** məhsulları axtara bilir — maya dəyəri (`unit_cost`) heç vaxt göstərilmir,
   yalnız ad/marka/miqdar/`marketplace_price`.
3. `MarketplaceOrder` yaradılır (status: **pending**).
4. Satıcı `accept()` — anbarından miqdar düşür (rezerv olunur).
5. `mark_paid()` — satıcının kassasına gəlir yazılır.
6. `mark_shipped()` → `mark_completed()` — alıcının **öz** anbarında avtomatik yeni məhsul sətri yaranır/artır.

Bu, tenant-təcrid qaydasının yeganə **qəsdən** istisnasıdır və yalnız bu modelin öz metodları
üzərindən idarə olunur ki, sərhəd aydın qalsın.

Seed skripti (`seed_demo.py`) iki mağaza yaradır (TechFix Servis — Bakı, MobilTəmir Gəncə) və
tam bir marketplace sifarişi nümunəsi ilə gəlir.

## Multi-tenant təhlükəsizlik prinsipi
Hər cədvəl `shop` (Mağaza) sahəsinə malikdir. **Növbəti addımda** hazırlanacaq API
qatında hər sorğu **mütləq** cari istifadəçinin `request.user.shop`-u ilə filtrlənəcək —
beləliklə bir mağazanın işçisi başqa mağazanın məlumatına heç vaxt çıxış əldə edə bilməyəcək
(dizaynda qeyd olunan tenant-təcrid tələbi).

## Növbəti addım
DRF serializers + viewsets + JWT login endpoint (`/api/auth/login/`), sonra Next.js frontend.
