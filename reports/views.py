import datetime
from decimal import Decimal

from django.db.models import Sum, Count
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from accounts.mixins import HasModulePermission
from accounts.models import Module
from customers.models import Customer
from repairs.models import RepairOrder, RepairPayment, RepairStatus, PaymentStatus
from finance.models import CashTransaction, TransactionType, compute_cashbox_summary
from suppliers.models import Supplier
from marketplace.models import MarketplaceOrder, OrderStatus


class DashboardView(APIView):
    """GET /api/dashboard/ — '02 Dashboard' səhifəsi üçün bütün KPI-lar."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        shop = request.user.shop
        if not shop:
            return Response({"detail": "Mağaza tapılmadı."}, status=400)

        today = timezone.now().date()
        month_start = today.replace(day=1)

        repairs = RepairOrder.objects.filter(shop=shop)
        active_statuses = [RepairStatus.RECEIVED, RepairStatus.DIAGNOSING,
                            RepairStatus.WAITING_REPAIR, RepairStatus.IN_PROGRESS]

        # Kassa səhifəsindəki "Mədaxil" ilə EYNİ məntiq: bir xidmət ləğv edilib pulu geri
        # qaytarılırsa, bu, "bu günün/ayın gəliri"ndən də çıxılmalıdır — əks halda ləğv
        # edəndən sonra bu rəqəm "dəyişmir" təəssüratı yaradır (məhz bu şikayət idi).
        today_income_gross = (CashTransaction.objects.filter(
            shop=shop, type=TransactionType.INCOME, created_at__date=today
        ).aggregate(s=Sum("amount"))["s"] or Decimal("0"))
        today_refund = (CashTransaction.objects.filter(
            shop=shop, type=TransactionType.REFUND, created_at__date=today
        ).aggregate(s=Sum("amount"))["s"] or Decimal("0"))
        # Köhnə (bu gün/bu ay daxil olmayan) bir satışın bu gün ləğv edilib geri
        # qaytarılması, "bu günün gəliri"ni MƏNFİ göstərməməlidir — "bu gün -270 AZN
        # gəlir" mənasız görünür (bu günün özündə heç bir satış olmaya bilər). Kassa
        # səhifəsindəki ümumi, tarixsiz "Mədaxil" fərqli olaraq həmişə müsbətdir, çünki
        # hər geri qaytarma özündən əvvəlki gəlirin bir hissəsini çıxır; burda isə
        # pəncərə (gün/ay) ilə məhdudlaşdırıldığı üçün mənfiyə düşə bilər — 0-da saxlanılır.
        today_income = max(today_income_gross - today_refund, Decimal("0"))

        month_income_gross = (CashTransaction.objects.filter(
            shop=shop, type=TransactionType.INCOME, created_at__date__gte=month_start
        ).aggregate(s=Sum("amount"))["s"] or Decimal("0"))
        month_refund = (CashTransaction.objects.filter(
            shop=shop, type=TransactionType.REFUND, created_at__date__gte=month_start
        ).aggregate(s=Sum("amount"))["s"] or Decimal("0"))
        month_income = max(month_income_gross - month_refund, Decimal("0"))

        customer_debt_total = sum(
            (r.remaining_debt for r in repairs.filter(payment_status=PaymentStatus.DEBT)), Decimal("0")
        )
        supplier_debt_total = sum((s.total_debt for s in Supplier.objects.filter(shop=shop)), Decimal("0"))

        warranty_active = [r for r in repairs if r.status != RepairStatus.CANCELLED
                           and r.warranty_days_left is not None and r.warranty_days_left >= 0]
        warranty_ending_soon = [r for r in warranty_active if r.warranty_days_left <= 3]

        overdue_repairs = repairs.exclude(status=RepairStatus.CANCELLED).filter(
            payment_status=PaymentStatus.DEBT, debt_due_date__lt=today
        ).count()

        recent = repairs.select_related("customer").order_by("-created_at")[:6]

        data = {
            "date": today,
            "customers_total": Customer.objects.filter(shop=shop).count(),
            "customers_new_this_week": Customer.objects.filter(
                shop=shop, created_at__date__gte=today - datetime.timedelta(days=7)).count(),
            "active_repairs_count": repairs.filter(status__in=active_statuses).count(),
            "today_income": today_income,
            "today_payments_count": CashTransaction.objects.filter(
                shop=shop, type=TransactionType.INCOME, created_at__date=today).count(),
            "month_income": month_income,
            "active_warranty_count": len(warranty_active),
            "warranty_ending_soon_count": len(warranty_ending_soon),
            "customer_debt_total": customer_debt_total,
            "supplier_debt_total": supplier_debt_total,
            "overdue_repairs_count": overdue_repairs,
            "recent_repairs": [
                {
                    "id": r.id, "number": r.number,
                    "customer_name": r.customer.full_name,
                    "customer_initials": r.customer.initials,
                    "device": f"{r.device_brand} {r.device_model}".strip(),
                    "work": r.issue_description,
                    "status": r.status, "status_label": r.get_status_display(),
                    "sale_price": r.sale_price,
                } for r in recent
            ],
        }
        # Gəlir rəqəmləri yalnız 'revenue_numbers' icazəsi olan rola göstərilir
        # (məs. şəyird təmirləri görür, amma gəliri yox).
        if not request.user.has_module_permission(Module.REVENUE_NUMBERS):
            data["today_income"] = None
            data["month_income"] = None
            data["today_payments_count"] = None
            data["revenue_hidden"] = True

        # Kassa balansı — Kassa səhifəsi ilə EYNİ hesablamadan (compute_cashbox_summary),
        # xərc və təchizatçı ödənişi artıq düşülmüş halda. Bu, 'kassa' modulu icazəsi olan
        # rola göstərilir (gəlir/mənfəət icazəsindən fərqli — kassiyyər mənfəəti görməyə bilər,
        # amma kassa balansını görməlidir).
        if request.user.has_module_permission(Module.CASHBOX):
            data["cash_balance"] = compute_cashbox_summary(shop)["current_balance"]
        else:
            data["cash_balance"] = None
        return Response(data)


class ReportsSummaryView(APIView):
    """GET /api/reports/summary/?start=YYYY-MM-DD&end=YYYY-MM-DD — '09 Hesabatlar' səhifəsi."""
    permission_classes = [IsAuthenticated, HasModulePermission]
    module_code = Module.REPORTS

    def get(self, request):
        if not request.user.has_module_permission(Module.REVENUE_NUMBERS):
            return Response({"detail": "Gəlir və mənfəət hesabatlarına icazəniz yoxdur."}, status=403)
        shop = request.user.shop
        today = timezone.now().date()
        start = request.query_params.get("start") or today.replace(day=1).isoformat()
        end = request.query_params.get("end") or today.isoformat()

        # DİQQƏT (əsas dəyişiklik — "pul ödənilməyibsə, hesabatlara düşməsin" tələbi):
        # əvvəllər "satış" (total_sales) və "maya dəyəri" (total_cost) təmir YARADILAN
        # kimi (created_at-a görə) hesablanırdı — borc olsa belə, hətta heç nə
        # ödənilməsə belə, rəqəm elə həmin an Hesabatlara düşürdü. İstifadəçinin dediyi
        # kimi: Kassadakı məntiq eyni olmalıdır — pul REAL daxil olanda (RepairPayment)
        # "satış", REAL xərclənəndə (SUPPLIER_PAYMENT) "maya dəyəri" sayılmalıdır. İndi
        # hər ikisi REAL pul hərəkətlərinə (CashTransaction/RepairPayment-in tarixinə)
        # görə hesablanır, təmirin YARADILMA tarixinə görə yox.
        repairs = RepairOrder.objects.filter(
            shop=shop, created_at__date__gte=start, created_at__date__lte=end
        ).exclude(status=RepairStatus.CANCELLED)

        sales_rows = (RepairPayment.objects.filter(
            repair__shop=shop, paid_at__date__gte=start, paid_at__date__lte=end,
        ).exclude(repair__status=RepairStatus.CANCELLED).select_related("repair"))
        total_sales = sum((p.amount for p in sales_rows), Decimal("0"))

        # Maya dəyəri (DÜZƏLİŞ — "borc ilə alınan hissə mənfəəti şişirdir" şikayəti):
        # ƏVVƏLKİ versiya maya dəyərini YALNIZ təchizatçıya REAL ödəniş ediləndə (SUPPLIER_
        # PAYMENT) tanıyırdı. Bu, detal TƏCHİZATÇIDAN BORC götürülüb təmir dərhal müştəriyə
        # satılanda (müştəri İSƏ dərhal ödəyəndə) səhv nəticə verirdi: satış (gəlir) dərhal
        # tanınır, maya dəyəri isə (təchizatçıya hələ ödənilmədiyi üçün) SIFIR sayılırdı —
        # nəticədə mənfəət süni şəkildə TAM satış qədər (borcu ödəyənə qədər) şişmiş görünürdü.
        # İstifadəçinin sözləri ilə: "mən borcu ödəməsəm belə, kassaya gələn məbləğ TAM
        # mənfəət kimi yazılır" — bu düzgün məntiq deyil, çünki təchizatçıya olan borc HƏR
        # HALDA real bir öhdəlikdir (geri ödəniləcək), sadəcə ödənişi gecikib.
        #
        # Düzgün (uyğunlaşdırma/"matching") prinsipi: hər təmirin maya dəyəri (cost_price)
        # onun SATIŞI tanınanda — yəni müştəri ÖDƏYƏNDƏ — eyni nisbətdə tanınır, təchizatçıya
        # REAL ödənilib-ödənilməməsindən ASILI OLMAYARAQ. Təchizatçıya olan borc ayrıca,
        # özünün yerində ("supplier_debt_total" və "Təchizatçılar üzrə borc" cədvəli ilə)
        # göstərilməyə davam edir — bu DƏYİŞMİR, sadəcə artıq mənfəəti SÜNİ ŞİŞİRTMİR.
        # Hissəvi ödənişlərdə maya dəyəri ödənilən hissəyə MÜTƏNASİB tanınır (məs. satış
        # 100 AZN, maya 40 AZN, indi 50 AZN ödənilirsə — bu ödənişlə 20 AZN maya "açılır").
        #
        # Təmirlə ƏLAQƏSİ OLMAYAN təchizatçı ödənişləri (məs. ümumi anbar doldurulması, heç
        # bir konkret satışla "qarşılaşdırılası" olmayan) köhnə qayda ilə — REAL ödənildiyi
        # an (cash-basis) — qalır, çünki bunların qarşılığında burada hesablanan bir "satış"
        # yoxdur ki, maya dəyərini onunla eyni ana "bağlayaq".
        cost_from_repairs = Decimal("0")
        for p in sales_rows:
            r = p.repair
            if r.sale_price and r.cost_price:
                cost_from_repairs += (r.cost_price * p.amount / r.sale_price)

        cost_paid_unrelated = (CashTransaction.objects.filter(
            shop=shop, type=TransactionType.SUPPLIER_PAYMENT, repair__isnull=True,
            created_at__date__gte=start, created_at__date__lte=end,
        ).aggregate(s=Sum("amount"))["s"] or Decimal("0"))
        cost_recovered = (CashTransaction.objects.filter(
            shop=shop, type=TransactionType.EXPENSE_REFUND, repair__isnull=True,
            created_at__date__gte=start, created_at__date__lte=end,
        ).aggregate(s=Sum("amount"))["s"] or Decimal("0"))
        total_cost = cost_from_repairs + cost_paid_unrelated - cost_recovered

        expenses = (CashTransaction.objects.filter(
            shop=shop, type=TransactionType.EXPENSE, created_at__date__gte=start, created_at__date__lte=end
        ).aggregate(s=Sum("amount"))["s"] or Decimal("0"))

        # Xidmət ləğv edilib geri qaytarılan məbləğ xalis mənfəətdən çıxılmamalıdır —
        # bu xidmətin satışı (sale_price) artıq total_sales-a daxil deyil (yuxarıdakı
        # .exclude(status=CANCELLED)), ona görə onun geri qaytarmasını bir də mənfəətdən
        # çıxsaq, heç olmayan "gəliri" iki dəfə mənfi hesablamış olarıq. Yalnız real
        # zəmanət qaytarması (aktiv/tamamlanmış təmirə bağlı) mənfəəti azaltmalıdır.
        #
        # DİQQƏT (bax: repairs/serializers.py-dəki RESTORE_MARK düzəlişi): sadəcə
        # "repair.status == CANCELLED-dirsə çıxma" kafi deyil. Əgər təmir LƏĞV EDİLİB
        # SONRA YENİDƏN AKTİVLƏŞDİRİLİBSƏ, köhnə ləğv zamanı yaradılmış REFUND sətri
        # bazada qalır, amma indi repair.status artıq CANCELLED DEYİL — ona görə əvvəlki
        # sadə filtr bu köhnə REFUND-u "real zəmanət qaytarması" kimi sayıb hər ləğv+bərpa
        # dövründə mənfəətdən bir də (səhvən) çıxırdı ("hər dəfə 50 mənfiyə aparır" şikayəti
        # məhz bu idi). Düzgün qayda: əgər bu REFUND artıq eyni təmir+üsul üzrə bərpa edici
        # INCOME (RESTORE_MARK） ilə "örtülübsə", demək pul artıq Kassaya qaytarılıb və bu
        # REFUND daha "real" itki sayılmamalıdır — yalnız HƏLƏ BƏRPA OLUNMAMIŞ xalis hissə
        # mənfəətdən çıxılır.
        from collections import defaultdict
        RESTORE_MARK = "yenidən aktivləşdirildi"

        refund_rows = list(CashTransaction.objects.filter(
            shop=shop, type=TransactionType.REFUND, created_at__date__gte=start, created_at__date__lte=end
        ).select_related("repair"))

        refunds = Decimal("0")
        counted_repair_methods = set()
        for t in refund_rows:
            if t.repair_id is None:
                refunds += t.amount
                continue
            if t.repair.status == RepairStatus.CANCELLED:
                # Təmir HAZIRDA ləğv olunmuş vəziyyətdədir — satışı onsuz da total_sales-a
                # daxil deyil, ona görə geri qaytarmasını mənfəətdən çıxmırıq.
                continue
            key = (t.repair_id, t.method)
            if key in counted_repair_methods:
                continue  # Eyni təmir+üsul üzrə yalnız BİR dəfə hesablanır (aşağıda cəmi özü aparılır).
            counted_repair_methods.add(key)

            total_refunded = CashTransaction.objects.filter(
                repair_id=t.repair_id, type=TransactionType.REFUND, method=t.method,
            ).aggregate(s=Sum("amount"))["s"] or Decimal("0")
            total_restored = CashTransaction.objects.filter(
                repair_id=t.repair_id, type=TransactionType.INCOME, method=t.method,
                description__icontains=RESTORE_MARK,
            ).aggregate(s=Sum("amount"))["s"] or Decimal("0")
            unrestored_total = max(total_refunded - total_restored, Decimal("0"))

            refund_in_period = CashTransaction.objects.filter(
                repair_id=t.repair_id, type=TransactionType.REFUND, method=t.method,
                created_at__date__gte=start, created_at__date__lte=end,
            ).aggregate(s=Sum("amount"))["s"] or Decimal("0")
            refunds += min(refund_in_period, unrestored_total)

        customer_debt = sum((r.remaining_debt for r in RepairOrder.objects.filter(
            shop=shop, payment_status=PaymentStatus.DEBT)), Decimal("0"))
        supplier_debt = sum((s.total_debt for s in Supplier.objects.filter(shop=shop)), Decimal("0"))

        # Xidmət üzrə bölgü də eyni REAL-pul məntiqinə köçürülür ki, aşağıdakı cədvəl
        # yuxarıdakı ümumi rəqəmlərlə ZİDDİYYƏT TƏŞKİL ETMƏSİN (əvvəllər bu, hələ də
        # köhnə "yaradılan kimi sayılır" məntiqini işlədirdi).
        by_service_sales: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        by_service_repairs: dict[str, set] = defaultdict(set)
        for p in sales_rows:
            key = p.repair.issue_description
            by_service_sales[key] += p.amount
            by_service_repairs[key].add(p.repair_id)

        # Maya dəyəri bölgüsü də yuxarıdakı eyni uyğunlaşdırma (matching) qaydası ilə —
        # ödənişə MÜTƏNASİB, təchizatçıya real ödənilib-ödənilməməsindən asılı olmadan
        # (bax: yuxarıdakı `cost_from_repairs` izahı). sales_rows artıq ləğv olunmuş
        # təmirləri çıxarıb, ona görə burda əlavə bir "cancelled" filtri lazım deyil.
        by_service_cost: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for p in sales_rows:
            r = p.repair
            if r.sale_price and r.cost_price:
                by_service_cost[r.issue_description] += (r.cost_price * p.amount / r.sale_price)

        # Ləğv olunub geri qaytarılan (xərc + geri qaytarma bir-birini tam sıfırlayan)
        # və heç bir ödəniş almayan xidmətlər cədvəldə "0 ədəd · 0 AZN" kimi boş sətir
        # kimi görünməməlidir — ona görə satışı VƏ maya dəyəri hər ikisi düz sıfır olan
        # sətirləri siyahıdan çıxarırıq.
        by_service = sorted((
            {
                "issue_description": key,
                "count": len(by_service_repairs.get(key, ())),
                "sales": by_service_sales.get(key, Decimal("0")),
                "cost": by_service_cost.get(key, Decimal("0")),
            }
            for key in (set(by_service_sales) | set(by_service_cost))
            if by_service_sales.get(key, Decimal("0")) != 0 or by_service_cost.get(key, Decimal("0")) != 0
        ), key=lambda r: -r["sales"])[:8]

        # Borcu olmayan təchizatçı "Təchizatçılar üzrə borc" siyahısında boş sətir
        # kimi görünməsin — yalnız real borcu olanlar göstərilir.
        by_supplier = [
            {"name": s.name, "purchased": s.total_purchased, "paid": s.total_paid, "debt": s.total_debt}
            for s in Supplier.objects.filter(shop=shop)
            if s.total_debt and s.total_debt != 0
        ]

        # Marketplace (digər mağazalara satış) — əvvəllər bu hesabata heç düşmürdü,
        # "qazanc"/"profit" yalnız öz müştərilərimizə olan təmirlərdən hesablanırdı.
        # Marketplace satışı bu mağaza üçün də real gəlir/qazanc yaradır, ona görə
        # ayrıca sətirlər kimi əlavə edirik (mövcud total_sales/total_cost/total_profit-i
        # DƏYİŞMİRİK ki, başqa yerdə bu sahələrə etibar edən kod pozulmasın).
        mp_sales = MarketplaceOrder.objects.filter(
            seller_shop=shop, status__in=[OrderStatus.PAID, OrderStatus.SHIPPED, OrderStatus.COMPLETED],
            paid_at__date__gte=start, paid_at__date__lte=end,
        )
        marketplace_sales_total = Decimal("0")
        marketplace_cost_total = Decimal("0")
        for o in mp_sales.select_related("product"):
            marketplace_sales_total += o.total_price
            marketplace_cost_total += (o.product.unit_cost or Decimal("0")) * o.quantity
        marketplace_profit = marketplace_sales_total - marketplace_cost_total

        return Response({
            "period": {"start": start, "end": end},
            "total_sales": total_sales,
            "total_cost": total_cost,
            "total_profit": total_sales - total_cost,
            "total_expense": expenses,
            "total_refund": refunds,
            "marketplace_sales_total": marketplace_sales_total,
            "marketplace_cost_total": marketplace_cost_total,
            "marketplace_profit": marketplace_profit,
            "net_profit": (total_sales - total_cost) - expenses - refunds + marketplace_profit,
            "customer_debt_total": customer_debt,
            "supplier_debt_total": supplier_debt,
            "repair_count": repairs.count(),
            "customer_count": Customer.objects.filter(shop=shop).count(),
            "by_service": [
                {"service": r["issue_description"], "count": r["count"],
                 "sales": r["sales"] or 0, "cost": r["cost"] or 0,
                 "profit": (r["sales"] or 0) - (r["cost"] or 0)}
                for r in by_service
            ],
            "by_supplier": by_supplier,
        })