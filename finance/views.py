from decimal import Decimal
from rest_framework import viewsets, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from accounts.mixins import ShopScopedQuerysetMixin, HasModulePermission
from accounts.models import Module
from .models import CashTransaction, TransactionType, CashboxOpeningBalance, compute_cashbox_summary
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


class CashboxSummaryView(APIView):
    """Kassa səhifəsinin üst hissəsi — başlanğıc + gəlir - xərc - ödəniş."""
    permission_classes = [IsAuthenticated, HasModulePermission]
    module_code = Module.CASHBOX

    def get(self, request):
        shop = request.user.shop
        return Response(compute_cashbox_summary(shop))