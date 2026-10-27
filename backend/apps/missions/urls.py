from rest_framework.routers import DefaultRouter

from .views import HazardAssessmentViewSet, MissionApprovalLogViewSet, MissionViewSet

router = DefaultRouter()
router.register('profiles', MissionViewSet, basename='mission')
router.register('hazards', HazardAssessmentViewSet, basename='hazard-assessment')
router.register('approval-logs', MissionApprovalLogViewSet, basename='mission-approval-log')

urlpatterns = router.urls
