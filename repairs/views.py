from django.conf import settings
from django.http import HttpResponse
from rest_framework import viewsets, filters, status, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from accounts.mixins import ShopScopedQuerysetMixin, HasModulePermission
from accounts.models import Module
from .models import RepairOrder, PaymentStatus, RepairWarrantyReturn, SupplierReturnStatus
from .serializers import (
    RepairOrderListSerializer, RepairOrderDetailSerializer,
    RepairStatusUpdateSerializer, RepairPaymentCreateSerializer,
    WarrantyReturnCreateSerializer, RepairWarrantyReturnSerializer,
    SupplierReturnDecisionSerializer,
)


def _render_warranty_pdf(repair):
    """
    Zəmanət PDF-ni yaradır. Standart PDF şriftləri (Helvetica və s.) Azərbaycan
    hərflərini (ə, ş, ğ, ı, ö, ü, ç) və "№" işarəsini çəkə bilmir — mətn boş
    qutular kimi çıxır. Ona görə repo-ya əlavə olunmuş DejaVu Sans şriftini
    (bütün bu simvolları əhatə edir) @font-face ilə PDF-ə göndəririk.
    """
    import io
    import pathlib
    from django.contrib.staticfiles import finders
    from django.template.loader import render_to_string
    from xhtml2pdf import pisa

    def _font_uri(name):
        path = finders.find(f"repairs/fonts/{name}")
        return pathlib.Path(path).as_uri() if path else ""

    html = render_to_string("repairs/warranty_pdf.html", {
        "repair": repair, "shop": repair.shop,
        "font_regular": _font_uri("DejaVuSans.ttf"),
        "font_bold": _font_uri("DejaVuSans-Bold.ttf"),
    })
    buf = io.BytesIO()
    pisa.CreatePDF(io.BytesIO(html.encode("utf-8")), dest=buf, encoding="utf-8")
    return buf


class RepairOrderViewSet(ShopScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = RepairOrder.objects.select_related("customer").prefetch_related("payments").all()
    permission_classes = [IsAuthenticated, HasModulePermission]
    module_code = Module.REPAIRS
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["status", "payment_status", "customer"]
    search_fields = ["number", "customer__full_name", "customer__phone", "device_imei", "device_serial"]
    ordering_fields = ["created_at", "sale_price"]

    def get_serializer_class(self):
        return RepairOrderDetailSerializer if self.action != "list" else RepairOrderListSerializer

    @action(detail=False, methods=["get"], url_path="device-suggestions")
    def device_suggestions(self, request):
        """
        Bu mağazanın əvvəlki təmirlərindən fərqli marka/model siyahısı — "Yeni xidmət"
        formasında marka/model sahələrinin avtomatik tamamlanması (datalist) üçün.
        """
        qs = self.get_queryset()
        brands = sorted({b for b in qs.values_list("device_brand", flat=True) if b})
        models_by_brand: dict[str, list[str]] = {}
        for brand, model in qs.values_list("device_brand", "device_model").distinct():
            if not brand or not model:
                continue
            models_by_brand.setdefault(brand, [])
            if model not in models_by_brand[brand]:
                models_by_brand[brand].append(model)
        all_models = sorted({m for ms in models_by_brand.values() for m in ms})
        return Response({"brands": brands, "models": all_models, "models_by_brand": models_by_brand})

    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, pk=None):
        repair = self.get_object()
        s = RepairStatusUpdateSerializer(data=request.data, context={"repair": repair})
        s.is_valid(raise_exception=True)
        s.save()
        return Response(RepairOrderDetailSerializer(repair).data)

    @action(detail=True, methods=["post"], url_path="payments")
    def add_payment(self, request, pk=None):
        repair = self.get_object()
        s = RepairPaymentCreateSerializer(data=request.data, context={"repair": repair, "request": request})
        s.is_valid(raise_exception=True)
        s.save()
        # get_object()-in prefetch_related("payments") keşi köhnəlmiş qalır (yeni ödəniş
        # bu keşdən sonra yaradılıb), ona görə cavab üçün təzə obyekt oxuyuruq.
        fresh = self.get_queryset().get(pk=repair.pk)
        return Response(RepairOrderDetailSerializer(fresh).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="warranty-return")
    def warranty_return(self, request, pk=None):
        """Zəmanət altında qaytarma yarat: maliyyəni düzəldir və (istəsə) təchizatçıya göndərir."""
        repair = self.get_object()
        s = WarrantyReturnCreateSerializer(data=request.data, context={"repair": repair, "request": request})
        s.is_valid(raise_exception=True)
        wr = s.save()
        fresh = self.get_queryset().get(pk=repair.pk)
        return Response(RepairOrderDetailSerializer(fresh, context={"request": request}).data,
                         status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="warranty-pdf")
    def warranty_pdf(self, request, pk=None):
        """Zəmanət sənədini PDF kimi qaytarır (çap/yükləmə üçün)."""
        repair = self.get_object()
        buf = _render_warranty_pdf(repair)
        # DİQQƏT: burada DRF-in Response() YOX, Django-nun HttpResponse()-u istifadə
        # olunur — DRF Response() cavabı JSON renderer-dən keçirməyə çalışır, PDF
        # baytlarını json.dumps() etmək isə "UnicodeDecodeError" ilə çökür.
        resp = HttpResponse(buf.getvalue(), content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="zemanet-{repair.number}.pdf"'
        return resp

    @action(detail=True, methods=["post"], url_path="warranty-email")
    def warranty_email(self, request, pk=None):
        """Zəmanət sənədini PDF olaraq müştərinin e-poçtuna göndərir (göndərən: mağazanın info@ ünvanı)."""
        from django.core.mail import EmailMessage

        repair = self.get_object()
        if not repair.customer.email:
            return Response({"detail": "Bu müştərinin e-poçt ünvanı qeydə alınmayıb."}, status=400)

        buf = _render_warranty_pdf(repair)

        email = EmailMessage(
            subject=f"{repair.shop.name} — Zəmanət sənədi ({repair.number})",
            body=(
                f"Salam {repair.customer.full_name},\n\n"
                f"{repair.number} nömrəli xidmətinizin zəmanət sənədi əlavədədir.\n\n"
                f"Hörmətlə,\n{repair.shop.name}"
            ),
            from_email=f"{repair.shop.name} <{settings.DEFAULT_FROM_EMAIL}>",
            to=[repair.customer.email],
            reply_to=[repair.shop.owner_email] if repair.shop.owner_email else None,
        )
        email.attach(f"zemanet-{repair.number}.pdf", buf.getvalue(), "application/pdf")
        email.send(fail_silently=False)
        return Response({"detail": "Göndərildi."})

    @action(detail=False, methods=["get"], url_path="warranties")
    def warranties(self, request):
        """'06 Zəmanətlər' səhifəsi — yalnız zəmanət başlamış (təhvil verilmiş) təmirlər."""
        qs = self.filter_queryset(self.get_queryset()).exclude(warranty_started_at__isnull=True)
        data = []
        for r in qs:
            data.append({
                "id": r.id, "number": r.number,
                "customer_id": r.customer_id,
                "customer_name": r.customer.full_name, "customer_initials": r.customer.initials,
                "customer_email": r.customer.email,
                "device": f"{r.device_brand} {r.device_model}".strip(),
                "work": r.issue_description,
                "warranty_started_at": r.warranty_started_at,
                "warranty_end_date": r.warranty_end_date,
                "warranty_days": r.warranty_days,
                "warranty_days_left": r.warranty_days_left,
            })
        data.sort(key=lambda x: (x["warranty_days_left"] is None, x["warranty_days_left"]))
        return Response(data)

    @action(detail=False, methods=["get"], url_path="debts")
    def debts(self, request):
        """'07 Borclar' səhifəsinin müştəri borcları hissəsi."""
        qs = self.filter_queryset(self.get_queryset()).filter(payment_status=PaymentStatus.DEBT)
        data = [{
            "id": r.id, "number": r.number,
            "customer_name": r.customer.full_name, "customer_initials": r.customer.initials,
            "reason": r.issue_description,
            "debt_date": r.received_at.date(), "due_date": r.debt_due_date,
            "amount": r.remaining_debt,
        } for r in qs]
        return Response(data)


class WarrantyReturnViewSet(ShopScopedQuerysetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                             viewsets.GenericViewSet):
    """Təchizatçıya göndərilmiş zəmanət qaytarmaları — Təchizatçılar səhifəsindən qəbul/rədd edilir."""
    queryset = RepairWarrantyReturn.objects.select_related(
        "repair", "repair__customer", "supplier_purchase", "supplier_purchase__supplier"
    ).all()
    serializer_class = RepairWarrantyReturnSerializer
    permission_classes = [IsAuthenticated, HasModulePermission]
    module_code = Module.SUPPLIERS
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["supplier_status"]

    @action(detail=True, methods=["patch"], url_path="resolve")
    def resolve(self, request, pk=None):
        wr = self.get_object()
        if wr.supplier_status not in (SupplierReturnStatus.PENDING, SupplierReturnStatus.NOT_SENT):
            return Response({"detail": "Bu qaytarma artıq həll olunub."}, status=400)
        s = SupplierReturnDecisionSerializer(data=request.data, context={"warranty_return": wr})
        s.is_valid(raise_exception=True)
        s.save()
        fresh = self.get_queryset().get(pk=wr.pk)
        return Response(RepairWarrantyReturnSerializer(fresh).data)