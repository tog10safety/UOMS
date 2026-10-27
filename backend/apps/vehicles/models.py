"""
Vehicle Tracking and Monitoring module — full Phase 2 build-out.

Vehicle.status/last_known_location already powered the Phase 1 dashboard;
this phase adds mission assignment, a location history trail, trip
history, and maintenance records.
"""
from django.contrib.gis.db import models as gis_models
from django.db import models

from apps.core.models import BaseModel
from apps.missions.models import Mission
from apps.personnel.models import Personnel


class Vehicle(BaseModel):
    class Status(models.TextChoices):
        AVAILABLE = 'AVAILABLE', 'Available'
        ON_MISSION = 'ON_MISSION', 'On Mission'
        MAINTENANCE = 'MAINTENANCE', 'Under Maintenance'
        OUT_OF_SERVICE = 'OUT_OF_SERVICE', 'Out of Service'

    class FuelType(models.TextChoices):
        DIESEL = 'DIESEL', 'Diesel'
        GASOLINE = 'GASOLINE', 'Gasoline'
        ELECTRIC = 'ELECTRIC', 'Electric'
        HYBRID = 'HYBRID', 'Hybrid'

    plate_number = models.CharField(max_length=20, unique=True)
    make = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=100, blank=True)
    vehicle_type = models.CharField(max_length=100, blank=True)
    year = models.PositiveIntegerField(null=True, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True, help_text='Passenger/cargo capacity.')
    fuel_type = models.CharField(max_length=20, choices=FuelType.choices, blank=True)
    odometer_km = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)
    assigned_driver = models.ForeignKey(
        Personnel, null=True, blank=True, on_delete=models.SET_NULL, related_name='assigned_vehicles'
    )
    assigned_mission = models.ForeignKey(
        Mission, null=True, blank=True, on_delete=models.SET_NULL, related_name='assigned_vehicles'
    )
    last_known_location = gis_models.PointField(geography=True, null=True, blank=True, srid=4326)
    last_location_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['vehicle_type']),
        ]

    def __str__(self):
        return self.plate_number


class VehicleLocationUpdate(BaseModel):
    """An immutable trail of location pings — powers a vehicle's track history."""

    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='location_history')
    location = gis_models.PointField(geography=True, srid=4326)
    speed_kph = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    heading_degrees = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    recorded_at = models.DateTimeField()

    class Meta(BaseModel.Meta):
        ordering = ['-recorded_at']
        indexes = [models.Index(fields=['vehicle', '-recorded_at'])]

    def __str__(self):
        return f'{self.vehicle.plate_number} @ {self.recorded_at:%Y-%m-%d %H:%M}'


class Trip(BaseModel):
    """A single dispatch/trip taken by a vehicle — the Trip History record."""

    class Status(models.TextChoices):
        ONGOING = 'ONGOING', 'Ongoing'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='trips')
    driver = models.ForeignKey(Personnel, on_delete=models.PROTECT, related_name='trips_driven')
    mission = models.ForeignKey(Mission, null=True, blank=True, on_delete=models.SET_NULL, related_name='trips')
    origin = models.CharField(max_length=200)
    destination = models.CharField(max_length=200)
    purpose = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ONGOING)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    start_odometer_km = models.PositiveIntegerField()
    end_odometer_km = models.PositiveIntegerField(null=True, blank=True)
    remarks = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=['vehicle', '-start_time']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f'{self.vehicle.plate_number}: {self.origin} → {self.destination}'

    @property
    def distance_km(self):
        if self.end_odometer_km is None:
            return None
        return self.end_odometer_km - self.start_odometer_km


class VehicleMaintenanceRecord(BaseModel):
    """A maintenance/service event for a vehicle."""

    class MaintenanceType(models.TextChoices):
        PREVENTIVE = 'PREVENTIVE', 'Preventive Maintenance'
        REPAIR = 'REPAIR', 'Repair'
        INSPECTION = 'INSPECTION', 'Inspection'
        TIRE_CHANGE = 'TIRE_CHANGE', 'Tire Change'
        OIL_CHANGE = 'OIL_CHANGE', 'Oil Change'
        OTHER = 'OTHER', 'Other'

    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='maintenance_records')
    maintenance_type = models.CharField(max_length=20, choices=MaintenanceType.choices)
    description = models.TextField(blank=True)
    performed_by = models.CharField(max_length=200, blank=True, help_text='Shop/technician name.')
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    service_date = models.DateField()
    next_due_date = models.DateField(null=True, blank=True)
    odometer_at_service_km = models.PositiveIntegerField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=['vehicle', '-service_date'])]

    def __str__(self):
        return f'{self.vehicle.plate_number} — {self.get_maintenance_type_display()} ({self.service_date})'
