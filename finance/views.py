from decimal import Decimal
from rest_framework import viewsets, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from accounts.mixins import ShopScopedQuerysetMixin, HasModulePermission
from accounts.models import Module
from .models import CashTransaction, TransactionType, CashboxOpeningBalance
from .serializers import CashTransactionSerializer


class CashTransactionViewSet(ShopScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = CashTransaction.objects.all()
    serializer_class = CashTransactionSerializer
    permission_classes = [IsAuthenticated, HasModulePermission]
    module_code = Module.CASHBOX
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["type"]
    ordering_fields = ["created_at"]


class CashboxSummaryView(APIView):
    """Kassa səhifəsinin üst hissəsi — başlanğıc + gəlir - xərc - ödəniş."""
    permission_classes = [IsAuthenticated, HasModulePermission]
    module_code = Module.CASHBOX

    def get(self, request):
        shop = request.user.shop
        opening = CashboxOpeningBalance.objects.filter(shop=shop).order_by("-as_of_date").first()
        opening_amount = opening.amount if opening else Decimal("0")

        qs = CashTransaction.objects.filter(shop=shop)
        income = sum((t.amount for t in qs.filter(type=TransactionType.INCOME)), Decimal("0"))
        expense = sum((t.amount for t in qs.filter(type=TransactionType.EXPENSE)), Decimal("0"))
        supplier_payment = sum((t.amount for t in qs.filter(type=TransactionType.SUPPLIER_PAYMENT)), Decimal("0"))
        refund = sum((t.amount for t in qs.filter(type=TransactionType.REFUND)), Decimal("0"))

        return Response({
            "opening_balance": opening_amount,
            "income": income,
            "expense": expense,
            "supplier_payment": supplier_payment,
            "refund": refund,
            "current_balance": opening_amount + income - expense - supplier_payment - refund,
        })
