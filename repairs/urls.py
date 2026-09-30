from rest_framework.routers import DefaultRouter
from .views import RepairOrderViewSet, WarrantyReturnViewSet

router = DefaultRouter()
# "warranty-returns" mütləq "" (RepairOrderViewSet) prefiksindən ƏVVƏL qeydiyyatdan keçməlidir,
# yoxsa router onu /repairs/{pk}/ kimi RepairOrderViewSet-ə göndərər.
router.register("warranty-returns", WarrantyReturnViewSet, basename="warranty-return")
router.register("", RepairOrderViewSet, basename="repair")
urlpatterns = router.urls
