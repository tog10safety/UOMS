from rest_framework.routers import DefaultRouter

from .views import TripViewSet, VehicleMaintenanceRecordViewSet, VehicleViewSet

router = DefaultRouter()
router.register('registry', VehicleViewSet, basename='vehicle')
router.register('trips', TripViewSet, basename='trip')
router.register('maintenance', VehicleMaintenanceRecordViewSet, basename='vehicle-maintenance')

urlpatterns = router.urls
