from rest_framework.routers import DefaultRouter
from .views import ProductViewSet, StockMovementViewSet

router = DefaultRouter()
router.register("products", ProductViewSet, basename="product")
router.register("movements", StockMovementViewSet, basename="stock-movement")
urlpatterns = router.urls
