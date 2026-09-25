from rest_framework.routers import DefaultRouter
from .views import CustomerViewSet

router = DefaultRouter()
router.register("", CustomerViewSet, basename="customer")
urlpatterns = router.urls
