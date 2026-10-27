from rest_framework.routers import DefaultRouter

from .views import PersonnelViewSet, PositionViewSet, QualificationViewSet, RankViewSet, SectionViewSet, UnitViewSet

router = DefaultRouter()
router.register('ranks', RankViewSet, basename='rank')
router.register('units', UnitViewSet, basename='unit')
router.register('sections', SectionViewSet, basename='section')
router.register('positions', PositionViewSet, basename='position')
router.register('qualifications', QualificationViewSet, basename='qualification')
router.register('records', PersonnelViewSet, basename='personnel')

urlpatterns = router.urls
