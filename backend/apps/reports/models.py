"""
Reports module.

Reports themselves are computed on the fly from existing data (see
apps.reports.services) rather than stored — this app's only model is an
audit trail of who exported what, when, and in which format.
"""
from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class ReportExportLog(BaseModel):
    class ReportType(models.TextChoices):
        PERSONNEL = 'PERSONNEL', 'Personnel Report'
        VEHICLE = 'VEHICLE', 'Vehicle Report'
        FLIGHT = 'FLIGHT', 'Flight Report'
        MISSION = 'MISSION', 'Mission Report'
        RISK = 'RISK', 'Risk Report'
        INVENTORY = 'INVENTORY', 'Inventory Report'

    class Format(models.TextChoices):
        PDF = 'PDF', 'PDF'
        XLSX = 'XLSX', 'Excel'

    report_type = models.CharField(max_length=20, choices=ReportType.choices)
    format = models.CharField(max_length=10, choices=Format.choices)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='report_exports',
    )
    row_count = models.PositiveIntegerField(default=0)

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=['report_type', '-created_at'])]

    def __str__(self):
        return f'{self.report_type} ({self.format}) by {self.generated_by} @ {self.created_at:%Y-%m-%d %H:%M}'
