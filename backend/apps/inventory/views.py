from django.db.models import Count, F, Q, Sum
from django.utils import timezone
from rest_framework import serializers as drf_serializers
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.audit import log_action
from apps.core.models import AuditLog
from apps.core.permissions import ModulePermissionMixin, UnitScopedQuerysetMixin
from apps.core.rbac import Action, Module

from .models import InventoryItem, InventoryTransaction, ItemCategory
from .serializers import InventoryItemSerializer, InventoryTransactionSerializer, ItemCategorySerializer


class ItemCategoryViewSet(ModulePermissionMixin, viewsets.ModelViewSet):
    queryset = ItemCategory.objects.all()
    serializer_class = ItemCategorySerializer
    permission_module = Module.INVENTORY
    search_fields = ['name']


class InventoryItemViewSet(ModulePermissionMixin, UnitScopedQuerysetMixin, viewsets.ModelViewSet):
    """Equipment/supply catalog with built-in stock levels and property accountability."""

    queryset = InventoryItem.objects.select_related('category', 'unit', 'accountable_personnel').all()
    serializer_class = InventoryItemSerializer
    permission_module = Module.INVENTORY
    filterset_fields = ['item_type', 'category', 'unit', 'condition', 'is_active']
    search_fields = ['name', 'property_number', 'sku']
    ordering_fields = ['name', 'quantity_on_hand', 'created_at']

    def perform_create(self, serializer):
        instance = serializer.save()
        log_action(
            user=self.request.user, action=AuditLog.Action.CREATE, instance=instance,
            description=f'Added inventory item "{instance.name}"', request=self.request,
        )

    def perform_update(self, serializer):
        instance = serializer.save()
        log_action(
            user=self.request.user, action=AuditLog.Action.UPDATE, instance=instance,
            description=f'Updated inventory item "{instance.name}"', request=self.request,
        )

    def perform_destroy(self, instance):
        log_action(
            user=self.request.user, action=AuditLog.Action.DELETE, instance=instance,
            description=f'Deactivated inventory item "{instance.name}"', request=self.request,
        )
        instance.is_active = False
        instance.save(update_fields=['is_active'])


class InventoryTransactionViewSet(ModulePermissionMixin, viewsets.ModelViewSet):
    """
    Every receiving/issuance/return/adjustment/disposal against an item.
    Creating a transaction here automatically updates the item's
    quantity_on_hand (and accountable_personnel for EQUIPMENT issuance),
    which is how "Stock levels" and "Property accountability" stay in sync.
    """

    queryset = InventoryTransaction.objects.select_related('item', 'issued_to', 'performed_by').all()
    serializer_class = InventoryTransactionSerializer
    permission_module = Module.INVENTORY
    action_permission_map = {
        # `create`'s actual required action depends on transaction_type, which we
        # don't know until the body is parsed — HasModulePermission runs before
        # that, so we grant on the broadest of ISSUE/CREATE here and let
        # perform_create's own business-rule checks (stock availability, etc.)
        # catch anything specific. Fine-grained per-transaction-type permission
        # checking would need a second check inside perform_create if you need
        # e.g. RETURN-only users blocked from ISSUANCE — not implemented yet.
        'create': Action.CREATE,
    }
    filterset_fields = ['item', 'transaction_type', 'issued_to']
    ordering_fields = ['transaction_date', 'created_at']

    def perform_create(self, serializer):
        instance = serializer.save(performed_by=self.request.user)
        item = instance.item

        if instance.transaction_type in (
            InventoryTransaction.TransactionType.RECEIPT,
            InventoryTransaction.TransactionType.RETURN,
        ):
            item.quantity_on_hand += instance.quantity
        elif instance.transaction_type in (
            InventoryTransaction.TransactionType.ISSUANCE,
            InventoryTransaction.TransactionType.DISPOSAL,
        ):
            if instance.quantity > item.quantity_on_hand:
                raise drf_serializers.ValidationError(
                    f'Cannot {instance.transaction_type.lower()} more than the {item.quantity_on_hand} on hand.'
                )
            item.quantity_on_hand -= instance.quantity
        elif instance.transaction_type == InventoryTransaction.TransactionType.ADJUSTMENT:
            # For an adjustment, `quantity` represents the corrected on-hand count directly.
            item.quantity_on_hand = instance.quantity

        update_fields = ['quantity_on_hand']

        is_equipment = item.item_type == InventoryItem.ItemType.EQUIPMENT
        if instance.transaction_type == InventoryTransaction.TransactionType.ISSUANCE and is_equipment:
            item.accountable_personnel = instance.issued_to
            update_fields.append('accountable_personnel')
        elif instance.transaction_type == InventoryTransaction.TransactionType.RETURN and is_equipment:
            item.accountable_personnel = None
            update_fields.append('accountable_personnel')

        item.save(update_fields=update_fields)

        log_action(
            user=self.request.user, action=AuditLog.Action.OTHER, instance=instance,
            description=f'{instance.get_transaction_type_display()}: {item.name} x{instance.quantity}',
            request=self.request,
        )


class InventoryReportView(APIView):
    """
    Inventory report — item counts, total stock, and low-stock flags
    grouped by category, for the Inventory Management "Inventory reports"
    view and for export in the dedicated Reports phase.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        items = InventoryItem.objects.filter(is_active=True).select_related('category')

        rows = (
            items.values(category_name=F('category__name'))
            .annotate(
                item_count=Count('id'),
                total_quantity_on_hand=Sum('quantity_on_hand'),
                low_stock_count=Count(
                    'id',
                    filter=Q(item_type=InventoryItem.ItemType.SUPPLY, quantity_on_hand__lte=F('reorder_level')),
                ),
            )
            .order_by('category_name')
        )

        by_category = [
            {
                'category': row['category_name'] or 'Uncategorized',
                'item_count': row['item_count'],
                'total_quantity_on_hand': row['total_quantity_on_hand'] or 0,
                'low_stock_count': row['low_stock_count'],
            }
            for row in rows
        ]

        return Response({
            'generated_at': timezone.now(),
            'total_items': items.count(),
            'total_low_stock': sum(1 for i in items if i.is_low_stock),
            'by_category': by_category,
        })
