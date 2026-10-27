"""
Risk alert feed used by the Dashboard's "Risk alerts" widget.

Full mission risk-assessment workflow (hazards, probability, severity,
controls, residual risk, approvals) lives in apps.missions in the
dedicated Mission Risk Management phase; this model is the lightweight
alert stream that surfaces on the main Dashboard.
"""
from django.db import models

from apps.core.models import BaseModel
from apps.missions.models import Mission


class RiskAlert(BaseModel):
    class Severity(models.TextChoices):
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'
        CRITICAL = 'CRITICAL', 'Critical'

    mission = models.ForeignKey(Mission, null=True, blank=True, on_delete=models.SET_NULL, related_name='risk_alerts')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.MEDIUM)
    is_resolved = models.BooleanField(default=False)

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=['severity', 'is_resolved'])]

    def __str__(self):
        return f'[{self.severity}] {self.title}'
