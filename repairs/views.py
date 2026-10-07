from django.conf import settings
from django.http import HttpResponse
from rest_framework import viewsets, filters, status, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from accounts.mixins import ShopScopedQuerysetMixin, HasModulePermission
from accounts.models import Module
from .models import RepairOrder, RepairStatus, RepairWarrantyReturn, SupplierReturnStatus
from .serializers import (
    RepairOrderListSerializer, RepairOrderDetailSerializer,
    RepairStatusUpdateSerializer, RepairPaymentCreateSerializer,
    WarrantyReturnCreateSerializer, RepairWarrantyReturnSerializer,
    SupplierReturnDecisionSerializer,
)


def _render_warranty_pdf(repair):
    """
    Zəmanət PDF-ni yaradır. Dizayn "display:flex" ilə qurulub (yan-yana başlıq/müştəri/
    cihaz sətirləri) — əvvəlki mühərrik olan xhtml2pdf (pisa) flex/grid dəstəkləmirdi, bu
    da PDF-də sətirlərin yan-yana yox, üst-üstə (sıralı) çıxmasına səbəb olurdu. WeasyPrint
    müasir CSS-i (flexbox daxil) düzgün dəstəklədiyi üçün dizaynın HTML/CSS kodu DƏYİŞMƏDƏN
    işləyir.

    Standart PDF şriftləri Azərbaycan hərflərini (ə, ş, ğ, ı, ö, ü, ç) çəkə bilmədiyi üçün
    repo-ya əlavə olunmuş DejaVu Sans şriftini @font-face ilə göndəririk (Google Fonts-dakı
    "Manrope" əvəzinə — PDF generasiyası zamanı xarici şriftə internet sorğusu etmək
    etibarsızdır: server şəbəkəsi məhdud ola bilər, bu da PDF-in sükutla yarımçıq çıxmasına
    səbəb olar).
    """
    import io
    import pathlib
    from django.contrib.staticfiles import finders
    from django.template.loader import render_to_string
    from weasyprint import HTML

    def _font_uri(name):
        path = finders.find(f"repairs/fonts/{name}")
        return pathlib.Path(path).as_uri() if path else ""

    def _fmt_date(dt):
        return dt.strftime("%d.%m.%Y") if dt else "—"

    def _fmt_time(dt):
        return dt.strftime("%H:%M") if dt else ""

    shop = repair.shop
    html = render_to_string("repairs/warranty_pdf.html", {
        "font_regular": _font_uri("DejaVuSans.ttf"),
        "font_bold": _font_uri("DejaVuSans-Bold.ttf"),
        "service_name": shop.name,
        "repair_id": repair.number,
        "delivery_date": _fmt_date(repair.delivered_at),
        "delivery_time": _fmt_time(repair.delivered_at),
        "customer_full_name": repair.customer.full_name,
        "customer_phone": repair.customer.phone,
        "device_brand": repair.device_brand,
        "device_model": repair.device_model,
        "device_serial": repair.device_imei or repair.device_serial or "—",
        "service_description": repair.work_done_note or repair.issue_description,
        "total_price": repair.sale_price,
        "warranty_days": repair.warranty_days,
        "warranty_start": _fmt_date(repair.warranty_started_at),
        "warranty_end": _fmt_date(repair.warranty_end_date),
        "service_phone": shop.phone,
        "service_address": shop.address,
    })
    buf = io.BytesIO()
    try:
        HTML(string=html).write_pdf(buf)
    except Exception as exc:
        # Çağıran tərəf (warranty_pdf/warranty_email action-ları) yalnız RuntimeError tutur —
        # WeasyPrint-in ata biləcəyi müxtəlif xəta tiplərini (şrift, parsing və s.) də həmin
        # tutma bloğunun işləməsi üçün RuntimeError-a çeviririk.
        raise RuntimeError(f"Zəmanət PDF-i yaradıla bilmədi (repair #{repair.pk}): {exc}") from exc
    # DİQQƏT: WeasyPrint xəta olanda exception atır (sükutla yarımçıq fayl qaytarmır), amma
    # hər ehtimala qarşı nəticənin boş olmadığını yenə də yoxlayırıq — yarımçıq/boş PDF faylı
    # mailə "boş əlavə" kimi getməsin, ya da yüklənəndə açılmayan sınıq fayl olmasın deyə.
    if not buf.getvalue():
        raise RuntimeError(f"Zəmanət PDF-i yaradıla bilmədi (repair #{repair.pk}).")
    return buf


class RepairOrderViewSet(ShopScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = RepairOrder.objects.select_related("customer").prefetch_related("payments", "status_history").all()
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
        try:
            buf = _render_warranty_pdf(repair)
        except RuntimeError as exc:
            # DİQQƏT: əvvəllər bu xəta sükutla udulurdu — server loguna heç nə yazılmırdı,
            # bu da server tərəfindəki əsl səbəbi tapmağı mümkünsüz edirdi. İndi tam traceback
            # `docker logs`-da görünür.
            import logging
            logging.getLogger("repairs").error("Zəmanət PDF generasiyası uğursuz oldu", exc_info=exc)
            return Response({"detail": "PDF yaradıla bilmədi — serverdə texniki xəta. Dəstəyə müraciət edin."}, status=500)
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

        try:
            buf = _render_warranty_pdf(repair)
        except RuntimeError as exc:
            import logging
            logging.getLogger("repairs").error("Zəmanət PDF generasiyası uğursuz oldu (mail)", exc_info=exc)
            return Response({"detail": "PDF yaradıla bilmədi, mail göndərilmədi — serverdə texniki xəta."}, status=500)

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
        pdf_bytes = buf.getvalue()
        email.attach(f"zemanet-{repair.number}.pdf", pdf_bytes, "application/pdf")
        try:
            email.send(fail_silently=False)
        except Exception as exc:
            # SMTP-nin özü rədd edəndə (autentifikasiya, limit, bağlantı və s.) bunu loglayırıq —
            # beləcə server logunda konkret səbəb görünür, "mail getmədi" şikayətində server
            # tərəfindən konkrit nə baş verdiyini araşdırmaq mümkün olur.
            import logging
            logging.getLogger("repairs").error(
                "Zəmanət e-poçtu göndərilmədi (repair #%s, PDF %s bayt): %s", repair.pk, len(pdf_bytes), exc
            )
            return Response({"detail": "Mail göndərilmədi — server/SMTP xətası. Server loquna baxın."}, status=502)
        return Response({"detail": "Göndərildi."})

    @action(detail=False, methods=["get"], url_path="warranties")
    def warranties(self, request):
        """'06 Zəmanətlər' səhifəsi — yalnız zəmanət başlamış (təhvil verilmiş) təmirlər."""
        # Təhvil verilib sonra ləğv edilmiş təmir (warranty_started_at artıq doldurulub) bu
        # siyahıdan çıxır — ləğv edilmiş xidmətə zəmanət şərti tətbiq olunmur.
        qs = (self.filter_queryset(self.get_queryset())
              .exclude(warranty_started_at__isnull=True)
              .exclude(status=RepairStatus.CANCELLED))
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
        """
        '07 Borclar' səhifəsinin müştəri borcları hissəsi.
        DİQQƏT: əvvəllər bura yalnız `payment_status=DEBT` olan təmirlər düşürdü — həmin sahə isə
        `recompute_payment_status()`-da YALNIZ status 'Təhvil verildi'-yə keçəndə 'debt' olur
        (bax repairs/models.py). Nəticədə, məs. 'Hazırdır' statusunda duran, hələ təhvil
        verilməmiş, qismən ödənilmiş bir təmirin qalıq borcu bu siyahıda HEÇ görünmürdü —
        halbuki müştərinin kart səhifəsindəki ümumi borc (bax customers/serializers.py
        get_total_debt) onu artıq hesaba qatırdı. İkisi fərqli nəticə göstərirdi deyə şikayət
        gəldi. Ona görə filtri 'status=DEBT'dən 'qalıq borc > 0 və ləğv edilməyib'ə dəyişdik —
        bu, get_total_debt ilə HƏM DƏ eyni məntiqdir.
        """
        qs = self.filter_queryset(self.get_queryset()).exclude(status=RepairStatus.CANCELLED)
        qs = [r for r in qs if r.remaining_debt > 0]
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