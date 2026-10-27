from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AmmunitionIssuanceViewSet,
    AmmunitionStockViewSet,
    ArmoryInspectionViewSet,
    ArmoryTransactionHistoryView,
    FirearmIssuanceViewSet,
    FirearmViewSet,
)

router = DefaultRouter()
router.register('firearms', FirearmViewSet, basename='firearm')
router.register('ammunition', AmmunitionStockViewSet, basename='ammunition-stock')
router.register('issuances', FirearmIssuanceViewSet, basename='firearm-issuance')
router.register('ammunition-issuances', AmmunitionIssuanceViewSet, basename='ammunition-issuance')
router.register('inspections', ArmoryInspectionViewSet, basename='armory-inspection')

urlpatterns = [
    path('transactions/', ArmoryTransactionHistoryView.as_view(), name='armory-transactions'),
] + router.urls
