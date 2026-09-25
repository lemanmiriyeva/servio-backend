from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView

from django.contrib.auth import get_user_model
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, filters

from .serializers import MyTokenObtainPairSerializer, MeSerializer, RoleSerializer
from .mixins import ShopScopedQuerysetMixin, HasModulePermission
from .models import Role, Module

User = get_user_model()


class LoginView(TokenObtainPairView):
    """POST /api/auth/token/  { username, password } -> access, refresh, user"""
    serializer_class = MyTokenObtainPairSerializer


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(MeSerializer(request.user).data)


class UserAdminSerializer(MeSerializer):
    class Meta(MeSerializer.Meta):
        fields = MeSerializer.Meta.fields + ["date_joined", "last_seen_at"]


class UserViewSet(ShopScopedQuerysetMixin, viewsets.ModelViewSet):
    """İstifadəçilər / Rollar səhifəsi üçün — yalnız öz mağazanın istifadəçiləri."""
    queryset = User.objects.select_related("role", "shop", "branch").all()
    serializer_class = UserAdminSerializer
    permission_classes = [IsAuthenticated, HasModulePermission]
    module_code = Module.USERS
    filter_backends = [filters.SearchFilter]
    search_fields = ["username", "first_name", "last_name", "phone", "email"]


class RoleViewSet(ShopScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Role.objects.prefetch_related("permissions").all()
    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticated, HasModulePermission]
    module_code = Module.USERS
