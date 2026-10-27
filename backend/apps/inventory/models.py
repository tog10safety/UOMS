"""
Inventory Management module.

Covers: equipment and supplies as InventoryItem records (with built-in
stock levels), issuance/receiving/adjustment via InventoryTransaction
(which also drives property accountability for serialized equipment),
and inventory reporting via the /inventory/report/ aggregation endpoint.
"""
from django.conf import settings
from django.db import models

from apps.core.models import BaseModel
from apps.personnel.models import Personnel, Unit


class ItemCategory(BaseModel):
    """Reference lookup — e.g. Communications, Medical, Tools, Rations."""

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        verbose_name_plural = 'Item categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class InventoryItem(BaseModel):
    """
    A catalog item — either serialized/accountable EQUIPMENT (tracked to
    a specific accountable person) or consumable SUPPLY (tracked purely
    by quantity_on_hand).
    """

    class ItemType(models.TextChoices):
        EQUIPMENT = 'EQUIPMENT', 'Equipment (Accountable)'
        SUPPLY = 'SUPPLY', 'Supply (Consumable)'

    class Condition(models.TextChoices):
        SERVICEABLE = 'SERVICEABLE', 'Serviceable'
        UNSERVICEABLE = 'UNSERVICEABLE', 'Unserviceable'
        FOR_DISPOSAL = 'FOR_DISPOSAL', 'For Disposal'

    name = models.CharField(max_length=200)
    category = models.ForeignKey(ItemCategory, null=True, blank=True, on_delete=models.SET_NULL, related_name='items')
    item_type = models.CharField(max_length=20, choices=ItemType.choices, default=ItemType.SUPPLY)
    property_number = models.CharField(
        max_length=50, blank=True, unique=False, help_text='Serial/property number (EQUIPMENT items only).'
    )
    sku = models.CharField(max_length=50, blank=True, help_text='Stock-keeping unit code, if any.')
    unit_of_measure = models.CharField(max_length=30, default='pcs')
    quantity_on_hand = models.PositiveIntegerField(default=0)
    reorder_level = models.PositiveIntegerField(default=0, help_text='Trigger a low-stock flag at or below this level.')
    condition = models.CharField(max_length=20, choices=Condition.choices, default=Condition.SERVICEABLE)
    unit = models.ForeignKey(
        Unit, null=True, blank=True, on_delete=models.SET_NULL, related_name='inventory_items',
        help_text='Owning AOR/unit.',
    )
    storage_location = models.CharField(max_length=150, blank=True)
    accountable_personnel = models.ForeignKey(
        Personnel, null=True, blank=True, on_delete=models.SET_NULL, related_name='accountable_equipment',
        help_text='Custodian formally accountable for this item (EQUIPMENT items only).',
    )
    description = models.TextField(blank=True)
    remarks = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=['item_type']),
            models.Index(fields=['unit']),
            models.Index(fields=['category']),
        ]

    def __str__(self):
        suffix = f' ({self.property_number})' if self.property_number else ''
        return f'{self.name}{suffix}'

    @property
    def is_low_stock(self):
        return self.item_type == self.ItemType.SUPPLY and self.quantity_on_hand <= self.reorder_level


class InventoryTransaction(BaseModel):
    """
    A single movement against an InventoryItem: receiving stock in,
    issuing it out (which sets accountable_personnel for EQUIPMENT),
    returns, adjustments (stock counts/corrections), and disposal.
    """

    class TransactionType(models.TextChoices):
        RECEIPT = 'RECEIPT', 'Receiving'
        ISSUANCE = 'ISSUANCE', 'Issuance'
        RETURN = 'RETURN', 'Return'
        ADJUSTMENT = 'ADJUSTMENT', 'Adjustment'
        DISPOSAL = 'DISPOSAL', 'Disposal'

    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    quantity = models.PositiveIntegerField(default=1)
    issued_to = models.ForeignKey(
        Personnel, null=True, blank=True, on_delete=models.SET_NULL, related_name='inventory_issuances',
    )
    supplier_or_source = models.CharField(max_length=200, blank=True, help_text='For RECEIPT transactions.')
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='inventory_transactions',
    )
    transaction_date = models.DateTimeField()
    reference_number = models.CharField(max_length=50, blank=True, help_text='PO#, DR#, or similar reference.')
    remarks = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=['item', '-transaction_date']),
            models.Index(fields=['transaction_type']),
        ]

    def __str__(self):
        return f'{self.get_transaction_type_display()}: {self.item.name} x{self.quantity}'
