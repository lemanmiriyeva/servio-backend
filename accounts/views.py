from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView

from django.contrib.auth import get_user_model
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, filters, serializers

from rest_framework.decorators import action

from .serializers import (
    MyTokenObtainPairSerializer, MeSerializer, RoleSerializer,
    UserWriteSerializer, SetPermissionsSerializer,
)
from .mixins import StrictShopScopedMixin, HasModulePermission
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


class UserViewSet(StrictShopScopedMixin, viewsets.ModelViewSet):
    """İstifadəçilər / Rollar səhifəsi üçün — yalnız öz mağazanın istifadəçiləri."""
    queryset = User.objects.select_related("role", "shop", "branch").filter(is_platform_admin=False).order_by("first_name", "username")
    permission_classes = [IsAuthenticated, HasModulePermission]
    module_code = Module.USERS
    filter_backends = [filters.SearchFilter]
    search_fields = ["username", "first_name", "last_name", "phone", "email"]

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return UserWriteSerializer
        return UserAdminSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx

    def perform_create(self, serializer):
        # UserWriteSerializer.create() shop-u özü təyin edir
        serializer.save()

    def perform_destroy(self, instance):
        # Öz hesabını silə bilməz, Sahib rolunu silə bilməz.
        if instance.id == self.request.user.id:
            raise serializers.ValidationError("Öz hesabınızı silə bilməzsiniz.")
        instance.status = User.Status.DISABLED
        instance.is_active = False
        instance.save(update_fields=["status", "is_active"])


class RoleViewSet(StrictShopScopedMixin, viewsets.ModelViewSet):
    queryset = Role.objects.prefetch_related("permissions").all()
    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticated, HasModulePermission]
    module_code = Module.USERS

    @action(detail=True, methods=["patch"], url_path="permissions")
    def set_permissions(self, request, pk=None):
        role = self.get_object()
        s = SetPermissionsSerializer(data=request.data, context={"role": role})
        s.is_valid(raise_exception=True)
        s.save()
        return Response(RoleSerializer(role).data)