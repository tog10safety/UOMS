from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AORBoundaryViewSet,
    CheckpointViewSet,
    LandingZoneViewSet,
    MapHazardViewSet,
    MapLayerViewSet,
    MGRSConvertView,
    MGRSParseView,
    OperationalOverlayView,
    RouteViewSet,
)

router = DefaultRouter()
router.register('aor-boundaries', AORBoundaryViewSet, basename='aor-boundary')
router.register('checkpoints', CheckpointViewSet, basename='checkpoint')
router.register('landing-zones', LandingZoneViewSet, basename='landing-zone')
router.register('hazards', MapHazardViewSet, basename='map-hazard')
router.register('routes', RouteViewSet, basename='gis-route')
router.register('layers', MapLayerViewSet, basename='map-layer')

urlpatterns = [
    path('overlay/', OperationalOverlayView.as_view(), name='gis-overlay'),
    path('mgrs-convert/', MGRSConvertView.as_view(), name='mgrs-convert'),
    path('mgrs-parse/', MGRSParseView.as_view(), name='mgrs-parse'),
] + router.urls
