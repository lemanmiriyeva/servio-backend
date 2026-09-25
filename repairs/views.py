from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from accounts.mixins import ShopScopedQuerysetMixin, HasModulePermission
from accounts.models import Module
from .models import RepairOrder, PaymentStatus
from .serializers import (
    RepairOrderListSerializer, RepairOrderDetailSerializer,
    RepairStatusUpdateSerializer, RepairPaymentCreateSerializer,
)


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

    @action(detail=False, methods=["get"], url_path="warranties")
    def warranties(self, request):
        """'06 Zəmanətlər' səhifəsi — yalnız zəmanət başlamış (təhvil verilmiş) təmirlər."""
        qs = self.filter_queryset(self.get_queryset()).exclude(warranty_started_at__isnull=True)
        data = []
        for r in qs:
            data.append({
                "id": r.id, "number": r.number,
                "customer_name": r.customer.full_name, "customer_initials": r.customer.initials,
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