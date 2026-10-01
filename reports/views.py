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
from repairs.models import RepairOrder, RepairStatus, PaymentStatus
from finance.models import CashTransaction, TransactionType
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

        today_income = (CashTransaction.objects.filter(
            shop=shop, type=TransactionType.INCOME, created_at__date=today
        ).aggregate(s=Sum("amount"))["s"] or Decimal("0"))

        month_income = (CashTransaction.objects.filter(
            shop=shop, type=TransactionType.INCOME, created_at__date__gte=month_start
        ).aggregate(s=Sum("amount"))["s"] or Decimal("0"))

        customer_debt_total = sum(
            (r.remaining_debt for r in repairs.filter(payment_status=PaymentStatus.DEBT)), Decimal("0")
        )
        supplier_debt_total = sum((s.total_debt for s in Supplier.objects.filter(shop=shop)), Decimal("0"))

        warranty_active = [r for r in repairs if r.warranty_days_left is not None and r.warranty_days_left >= 0]
        warranty_ending_soon = [r for r in warranty_active if r.warranty_days_left <= 3]

        overdue_repairs = repairs.filter(
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

        repairs = RepairOrder.objects.filter(
            shop=shop, created_at__date__gte=start, created_at__date__lte=end
        ).exclude(status=RepairStatus.CANCELLED)

        total_sales = repairs.aggregate(s=Sum("sale_price"))["s"] or Decimal("0")
        total_cost = repairs.aggregate(s=Sum("cost_price"))["s"] or Decimal("0")

        expenses = (CashTransaction.objects.filter(
            shop=shop, type=TransactionType.EXPENSE, created_at__date__gte=start, created_at__date__lte=end
        ).aggregate(s=Sum("amount"))["s"] or Decimal("0"))

        refunds = (CashTransaction.objects.filter(
            shop=shop, type=TransactionType.REFUND, created_at__date__gte=start, created_at__date__lte=end
        ).aggregate(s=Sum("amount"))["s"] or Decimal("0"))

        customer_debt = sum((r.remaining_debt for r in RepairOrder.objects.filter(
            shop=shop, payment_status=PaymentStatus.DEBT)), Decimal("0"))
        supplier_debt = sum((s.total_debt for s in Supplier.objects.filter(shop=shop)), Decimal("0"))

        by_service = (repairs.values("issue_description")
                      .annotate(count=Count("id"), sales=Sum("sale_price"), cost=Sum("cost_price"))
                      .order_by("-sales")[:8])

        by_supplier = [
            {"name": s.name, "purchased": s.total_purchased, "paid": s.total_paid, "debt": s.total_debt}
            for s in Supplier.objects.filter(shop=shop)
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