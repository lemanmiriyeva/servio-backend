from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from accounts.mixins import ShopScopedQuerysetMixin, HasModulePermission
from accounts.models import Module
from .models import Customer
from .serializers import CustomerSerializer


class CustomerViewSet(ShopScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated, HasModulePermission]
    module_code = Module.CUSTOMERS
    filter_backends = [filters.SearchFilter]
    search_fields = ["full_name", "phone", "email"]
