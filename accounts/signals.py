from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import DEFAULT_ROLE_MODULES, Module, Role, RolePermission


@receiver(post_save, sender=Role)
def create_default_permissions(sender, instance, created, raw=False, **kwargs):
    """Hər yeni rol üçün bütün modulların icazə sətri yaranır — əks halda rol heç nəyə icazəsiz qalırdı
    (istifadəçi yalnız Dashboard/Zəmanət/Bildiriş görürdü) və 'Rollar və icazələr' səhifəsində düymələr işləmirdi."""
    if raw or not created or instance.is_owner_role:
        return
    for m in Module.values:
        RolePermission.objects.get_or_create(
            role=instance, module=m, defaults={"is_allowed": m in DEFAULT_ROLE_MODULES}
        )
