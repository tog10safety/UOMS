from rest_framework.routers import DefaultRouter

from .views import AircraftViewSet, FlightCrewAssignmentViewSet, FlightViewSet

router = DefaultRouter()
router.register('registry', AircraftViewSet, basename='aircraft')
router.register('flights', FlightViewSet, basename='flight')
router.register('crew-assignments', FlightCrewAssignmentViewSet, basename='flight-crew-assignment')

urlpatterns = router.urls
