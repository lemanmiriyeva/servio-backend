import json
from decimal import Decimal
from rest_framework import viewsets, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, BasePermission
from django_filters.rest_framework import DjangoFilterBackend

from accounts.mixins import ShopScopedQuerysetMixin, HasModulePermission
from accounts.models import Module
from .models import CashTransaction, TransactionType, CashboxOpeningBalance, OperationLog, compute_cashbox_summary
from .serializers import CashTransactionSerializer


class CashTransactionViewSet(ShopScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = CashTransaction.objects.all()
    serializer_class = CashTransactionSerializer
    permission_classes = [IsAuthenticated, HasModulePermission]
    module_code = Module.CASHBOX
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    # "supplier" əlavə edildi — konkret təchizatçının ödəniş tarixçəsini
    # (?supplier=<id>&type=supplier_payment) göstərmək üçün (əvvəllər yalnız
    # "type" üzrə filtrləmək mümkün idi).
    filterset_fields = ["type", "supplier", "repair"]
    ordering_fields = ["created_at"]

    def perform_destroy(self, instance):
        from .oplog import deletion_actor
        with deletion_actor(self.request.user):
            instance.delete()


class IsShopAdminOrPlatform(BasePermission):
    message = "Bu bölmə yalnız admin üçündür."

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (u.is_platform_admin or u.is_superuser or u.is_shop_admin))


class OperationLogView(APIView):
    """GET /api/cashbox/operation-log/?kind=repair|cash — silinmiş əməliyyatlar (yalnız admin)."""
    permission_classes = [IsAuthenticated, IsShopAdminOrPlatform]

    def get(self, request):
        user = request.user
        qs = OperationLog.objects.all()
        # Platforma admini bütün mağazaların jurnalını görür; Mağaza admini yalnız öz mağazasınınkını.
        if not (user.is_platform_admin or user.is_superuser):
            if not user.shop_id:
                return Response([])
            qs = qs.filter(shop=user.shop_id)
        kind = request.query_params.get("kind")
        if kind in ("repair", "cash"):
            qs = qs.filter(kind=kind)
        out = []
        for o in qs.select_related("shop")[:300]:
            try:
                details = json.loads(o.details) if o.details else {}
            except ValueError:
                details = {}
            out.append({
                "id": o.id, "kind": o.kind, "title": o.title, "amount": o.amount, "details": details,
                "deleted_by": o.deleted_by_name, "deleted_at": o.deleted_at, "shop": o.shop.name,
            })
        return Response(out)


class CashboxSummaryView(APIView):
    """Kassa səhifəsinin üst hissəsi — başlanğıc + gəlir - xərc - ödəniş."""
    permission_classes = [IsAuthenticated, HasModulePermission]
    module_code = Module.CASHBOX

    def get(self, request):
        shop = request.user.shop
        return Response(compute_cashbox_summary(shop))