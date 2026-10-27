"""
Aircraft Flying Monitoring module — full Phase 2 build-out.

Covers: aircraft registry, flight scheduling, aircrew assignment, mission
linkage, origin/destination/itinerary, departure/arrival monitoring,
flight status, CAAP flight plan information, and AOR unit visibility
(via Aircraft.base_unit / Flight.unit).
"""
from django.contrib.gis.db import models as gis_models
from django.db import models

from apps.core.models import BaseModel
from apps.missions.models import Mission
from apps.personnel.models import Personnel, Unit


class Aircraft(BaseModel):
    class FlyingStatus(models.TextChoices):
        GROUNDED = 'GROUNDED', 'Grounded'
        SCHEDULED = 'SCHEDULED', 'Scheduled'
        IN_FLIGHT = 'IN_FLIGHT', 'In Flight'
        MAINTENANCE = 'MAINTENANCE', 'Under Maintenance'

    tail_number = models.CharField(max_length=20, unique=True)
    aircraft_type = models.CharField(max_length=100, blank=True)
    manufacturer = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=100, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True, help_text='Passenger/cargo capacity.')
    flying_status = models.CharField(max_length=20, choices=FlyingStatus.choices, default=FlyingStatus.GROUNDED)
    base_unit = models.ForeignKey(
        Unit, null=True, blank=True, on_delete=models.SET_NULL, related_name='based_aircraft',
        help_text='Owning AOR/unit — drives visibility scoping.',
    )

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=['flying_status']),
            models.Index(fields=['base_unit']),
        ]

    def __str__(self):
        return self.tail_number


class Flight(BaseModel):
    """A single scheduled/flown mission leg for an aircraft."""

    class Status(models.TextChoices):
        SCHEDULED = 'SCHEDULED', 'Scheduled'
        DEPARTED = 'DEPARTED', 'Departed'
        EN_ROUTE = 'EN_ROUTE', 'En Route'
        ARRIVED = 'ARRIVED', 'Arrived'
        DELAYED = 'DELAYED', 'Delayed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    flight_number = models.CharField(max_length=30, unique=True)
    aircraft = models.ForeignKey(Aircraft, on_delete=models.PROTECT, related_name='flights')
    mission = models.ForeignKey(Mission, null=True, blank=True, on_delete=models.SET_NULL, related_name='flights')
    unit = models.ForeignKey(
        Unit, null=True, blank=True, on_delete=models.SET_NULL, related_name='flights',
        help_text='AOR unit this flight is visible to.',
    )

    origin = models.CharField(max_length=150)
    origin_location = gis_models.PointField(geography=True, null=True, blank=True, srid=4326)
    destination = models.CharField(max_length=150)
    destination_location = gis_models.PointField(geography=True, null=True, blank=True, srid=4326)

    scheduled_departure = models.DateTimeField()
    scheduled_arrival = models.DateTimeField()
    actual_departure = models.DateTimeField(null=True, blank=True)
    actual_arrival = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)

    # CAAP (Civil Aviation Authority of the Philippines) flight plan information
    caap_flight_plan_number = models.CharField(max_length=50, blank=True)
    caap_aircraft_registration = models.CharField(max_length=20, blank=True)
    caap_remarks = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['aircraft', '-scheduled_departure']),
            models.Index(fields=['unit']),
        ]

    def __str__(self):
        return f'{self.flight_number}: {self.origin} → {self.destination}'


class FlightCrewAssignment(BaseModel):
    """Aircrew assigned to a flight (pilot, co-pilot, loadmaster, etc)."""

    class CrewRole(models.TextChoices):
        PILOT_IN_COMMAND = 'PIC', 'Pilot in Command'
        CO_PILOT = 'CO_PILOT', 'Co-Pilot'
        FLIGHT_ENGINEER = 'FLIGHT_ENGINEER', 'Flight Engineer'
        LOADMASTER = 'LOADMASTER', 'Loadmaster'
        CREW_CHIEF = 'CREW_CHIEF', 'Crew Chief'
        OTHER = 'OTHER', 'Other'

    flight = models.ForeignKey(Flight, on_delete=models.CASCADE, related_name='crew_assignments')
    personnel = models.ForeignKey(Personnel, on_delete=models.PROTECT, related_name='flight_assignments')
    crew_role = models.CharField(max_length=20, choices=CrewRole.choices)

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=['flight', 'personnel'], name='unique_crew_member_per_flight'),
        ]

    def __str__(self):
        return f'{self.personnel.full_name} — {self.get_crew_role_display()} on {self.flight.flight_number}'


class FlightWaypoint(BaseModel):
    """An ordered itinerary stop/waypoint for a flight."""

    flight = models.ForeignKey(Flight, on_delete=models.CASCADE, related_name='waypoints')
    sequence = models.PositiveIntegerField()
    name = models.CharField(max_length=150)
    location = gis_models.PointField(geography=True, null=True, blank=True, srid=4326)
    eta = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta(BaseModel.Meta):
        ordering = ['flight', 'sequence']
        constraints = [
            models.UniqueConstraint(fields=['flight', 'sequence'], name='unique_waypoint_sequence_per_flight'),
        ]

    def __str__(self):
        return f'{self.flight.flight_number} — waypoint {self.sequence}: {self.name}'
