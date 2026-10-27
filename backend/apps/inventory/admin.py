from django.contrib import admin

from .models import InventoryItem, InventoryTransaction, ItemCategory


@admin.register(ItemCategory)
class ItemCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active')
    search_fields = ('name',)


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'item_type', 'category', 'quantity_on_hand', 'reorder_level',
        'condition', 'unit', 'accountable_personnel', 'is_active',
    )
    list_filter = ('item_type', 'condition', 'category', 'unit', 'is_active')
    search_fields = ('name', 'property_number', 'sku')
    autocomplete_fields = ('category', 'unit', 'accountable_personnel')


@admin.register(InventoryTransaction)
class InventoryTransactionAdmin(admin.ModelAdmin):
    list_display = ('item', 'transaction_type', 'quantity', 'issued_to', 'transaction_date')
    list_filter = ('transaction_type',)
    autocomplete_fields = ('item', 'issued_to', 'performed_by')
