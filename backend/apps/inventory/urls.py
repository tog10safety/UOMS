from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import InventoryItemViewSet, InventoryReportView, InventoryTransactionViewSet, ItemCategoryViewSet

router = DefaultRouter()
router.register('categories', ItemCategoryViewSet, basename='item-category')
router.register('items', InventoryItemViewSet, basename='inventory-item')
router.register('transactions', InventoryTransactionViewSet, basename='inventory-transaction')

urlpatterns = [
    path('report/', InventoryReportView.as_view(), name='inventory-report'),
] + router.urls
