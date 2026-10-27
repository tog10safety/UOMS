"""
Armory Management module.

Covers: firearms registry, ammunition stock, accountable personnel,
issuance, return, inventory (on-hand quantities), inspection, and
transaction history (via FirearmIssuance/AmmunitionIssuance records,
surfaced together through the /armory/transactions/ endpoint).
"""
from django.conf import settings
from django.db import models

from apps.core.models import BaseModel
from apps.personnel.models import Personnel, Unit


class Firearm(BaseModel):
    class Status(models.TextChoices):
        SERVICEABLE = 'SERVICEABLE', 'Serviceable (In Armory)'
        ISSUED = 'ISSUED', 'Issued'
        UNSERVICEABLE = 'UNSERVICEABLE', 'Unserviceable'
        IN_REPAIR = 'IN_REPAIR', 'In Repair'
        DECOMMISSIONED = 'DECOMMISSIONED', 'Decommissioned'

    serial_number = models.CharField(max_length=50, unique=True)
    firearm_type = models.CharField(max_length=100, help_text='e.g. Rifle, Pistol, Machine Gun')
    make = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=100, blank=True)
    caliber = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SERVICEABLE)
    unit = models.ForeignKey(
        Unit, null=True, blank=True, on_delete=models.SET_NULL, related_name='firearms',
        help_text='Owning AOR/unit.',
    )
    accountable_personnel = models.ForeignKey(
        Personnel, null=True, blank=True, on_delete=models.SET_NULL, related_name='accountable_firearms',
        help_text='Armorer/custodian formally accountable for this weapon.',
    )
    acquisition_date = models.DateField(null=True, blank=True)
    remarks = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['unit']),
        ]

    def __str__(self):
        return f'{self.firearm_type} — {self.serial_number}'


class AmmunitionStock(BaseModel):
    ammunition_type = models.CharField(max_length=100, help_text='e.g. 5.56mm Ball')
    lot_number = models.CharField(max_length=50, blank=True)
    unit = models.ForeignKey(
        Unit, null=True, blank=True, on_delete=models.SET_NULL, related_name='ammunition_stocks',
    )
    quantity_on_hand = models.PositiveIntegerField(default=0)
    unit_of_measure = models.CharField(max_length=30, default='rounds')
    storage_location = models.CharField(max_length=150, blank=True)
    expiration_date = models.DateField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=['ammunition_type'])]
        constraints = [
            models.UniqueConstraint(
                fields=['ammunition_type', 'lot_number', 'unit'], name='unique_ammo_lot_per_unit'
            ),
        ]

    def __str__(self):
        return f'{self.ammunition_type} (Lot {self.lot_number or "N/A"}) — {self.quantity_on_hand} {self.unit_of_measure}'


class FirearmIssuance(BaseModel):
    class Status(models.TextChoices):
        ISSUED = 'ISSUED', 'Issued'
        RETURNED = 'RETURNED', 'Returned'
        OVERDUE = 'OVERDUE', 'Overdue'
        LOST = 'LOST', 'Lost / Missing'

    firearm = models.ForeignKey(Firearm, on_delete=models.CASCADE, related_name='issuances')
    issued_to = models.ForeignKey(Personnel, on_delete=models.PROTECT, related_name='firearm_issuances')
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='firearm_issuances_made',
    )
    issue_date = models.DateTimeField()
    expected_return_date = models.DateTimeField(null=True, blank=True)
    return_date = models.DateTimeField(null=True, blank=True)
    condition_on_issue = models.CharField(max_length=150, blank=True)
    condition_on_return = models.CharField(max_length=150, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ISSUED)
    purpose = models.CharField(max_length=255, blank=True)
    remarks = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=['firearm', '-issue_date']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f'{self.firearm.serial_number} → {self.issued_to.full_name} ({self.status})'


class AmmunitionIssuance(BaseModel):
    ammunition_stock = models.ForeignKey(AmmunitionStock, on_delete=models.CASCADE, related_name='issuances')
    issued_to = models.ForeignKey(Personnel, on_delete=models.PROTECT, related_name='ammunition_issuances')
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='ammo_issuances_made',
    )
    quantity = models.PositiveIntegerField()
    issue_date = models.DateTimeField()
    purpose = models.CharField(max_length=255, blank=True)
    remarks = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=['ammunition_stock', '-issue_date'])]

    def __str__(self):
        return f'{self.ammunition_stock.ammunition_type} x{self.quantity} → {self.issued_to.full_name}'


class ArmoryInspection(BaseModel):
    class Result(models.TextChoices):
        PASSED = 'PASSED', 'Passed'
        FAILED = 'FAILED', 'Failed'
        NEEDS_MAINTENANCE = 'NEEDS_MAINTENANCE', 'Needs Maintenance'

    firearm = models.ForeignKey(Firearm, null=True, blank=True, on_delete=models.SET_NULL, related_name='inspections')
    inspection_date = models.DateField()
    inspected_by = models.ForeignKey(Personnel, on_delete=models.PROTECT, related_name='armory_inspections')
    result = models.CharField(max_length=20, choices=Result.choices)
    findings = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=['-inspection_date'])]

    def __str__(self):
        target = self.firearm.serial_number if self.firearm else 'General armory'
        return f'{target} — {self.get_result_display()} ({self.inspection_date})'
