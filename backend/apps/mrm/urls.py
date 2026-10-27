from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AnalyticsView, ConfigView, FeedbackViewSet, FormViewSet, HazardViewSet, MeView, SafetyAssignmentViewSet,
    SafetyUserViewSet, SignatureView, UnitLogoViewSet, WorkQueueView,
)

router = DefaultRouter()
router.register('hazards', HazardViewSet, basename='mrm-hazard')
router.register('forms', FormViewSet, basename='mrm-form')
router.register('feedback', FeedbackViewSet, basename='mrm-feedback')
router.register('safety/users', SafetyUserViewSet, basename='mrm-safety-user')
router.register('safety/assignments', SafetyAssignmentViewSet, basename='mrm-safety-assignment')
router.register('unit-logos', UnitLogoViewSet, basename='mrm-unit-logo')

urlpatterns = [
    path('config/', ConfigView.as_view(), name='mrm-config'),
    path('me/', MeView.as_view(), name='mrm-me'),
    path('signature/', SignatureView.as_view(), name='mrm-signature'),
    path('work-queue/', WorkQueueView.as_view(), name='mrm-work-queue'),
    path('analytics/', AnalyticsView.as_view(), name='mrm-analytics'),
    path('', include(router.urls)),
]
