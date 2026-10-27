from rest_framework import serializers

from .models import InventoryItem, InventoryTransaction, ItemCategory


class ItemCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemCategory
        fields = ['id', 'name', 'description', 'is_active']


class InventoryItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True, default=None)
    unit_name = serializers.CharField(source='unit.name', read_only=True, default=None)
    accountable_personnel_name = serializers.CharField(
        source='accountable_personnel.full_name', read_only=True, default=None
    )
    is_low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = InventoryItem
        fields = [
            'id', 'name', 'category', 'category_name', 'item_type', 'property_number', 'sku',
            'unit_of_measure', 'quantity_on_hand', 'reorder_level', 'is_low_stock', 'condition',
            'unit', 'unit_name', 'storage_location', 'accountable_personnel', 'accountable_personnel_name',
            'description', 'remarks', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'quantity_on_hand', 'accountable_personnel', 'created_at', 'updated_at']

    def validate(self, attrs):
        item_type = attrs.get('item_type', getattr(self.instance, 'item_type', None))
        property_number = attrs.get('property_number', getattr(self.instance, 'property_number', ''))
        if item_type == InventoryItem.ItemType.EQUIPMENT and not property_number:
            raise serializers.ValidationError('property_number is required for EQUIPMENT items.')
        return attrs


class InventoryTransactionSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    issued_to_name = serializers.CharField(source='issued_to.full_name', read_only=True, default=None)
    performed_by_username = serializers.CharField(source='performed_by.username', read_only=True, default=None)

    class Meta:
        model = InventoryTransaction
        fields = [
            'id', 'item', 'item_name', 'transaction_type', 'quantity', 'issued_to', 'issued_to_name',
            'supplier_or_source', 'performed_by', 'performed_by_username', 'transaction_date',
            'reference_number', 'remarks', 'is_active', 'created_at',
        ]
        read_only_fields = ['id', 'performed_by', 'created_at']

    def validate(self, attrs):
        transaction_type = attrs.get('transaction_type')
        item = attrs.get('item') or getattr(self.instance, 'item', None)
        quantity = attrs.get('quantity', getattr(self.instance, 'quantity', None))

        if transaction_type == InventoryTransaction.TransactionType.ISSUANCE and not attrs.get('issued_to'):
            raise serializers.ValidationError('issued_to is required for an ISSUANCE transaction.')

        if transaction_type in (
            InventoryTransaction.TransactionType.ISSUANCE,
            InventoryTransaction.TransactionType.DISPOSAL,
        ) and item and quantity is not None and quantity > item.quantity_on_hand:
            raise serializers.ValidationError(
                f'Cannot {transaction_type.lower()} {quantity} {item.unit_of_measure} — '
                f'only {item.quantity_on_hand} on hand.'
            )
        return attrs


class InventoryReportItemSerializer(serializers.Serializer):
    """Row shape for the /inventory/report/ aggregation endpoint."""

    category = serializers.CharField()
    item_count = serializers.IntegerField()
    total_quantity_on_hand = serializers.IntegerField()
    low_stock_count = serializers.IntegerField()
