"""
GIS / Operational Mapping module.

Covers: AOR boundaries, mission locations (already on apps.missions.Mission),
checkpoints, landing zones, hazards, routes, operational overlays (via
MapLayer + the /gis/overlay/ aggregation endpoint), MGRS coordinates
(computed in serializers via apps.gis.utils.latlon_to_mgrs), and map layers.
"""
from django.contrib.gis.db import models as gis_models
from django.db import models

from apps.core.models import BaseModel
from apps.personnel.models import Personnel, Unit


class AORBoundary(BaseModel):
    """A polygon defining a unit's Area of Responsibility."""

    name = models.CharField(max_length=150)
    unit = models.ForeignKey(Unit, null=True, blank=True, on_delete=models.SET_NULL, related_name='aor_boundaries')
    boundary = gis_models.PolygonField(geography=True, srid=4326)
    color = models.CharField(max_length=20, default='#22d3ee', help_text='Hex color for map rendering.')
    description = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=['unit'])]

    def __str__(self):
        return self.name


class Checkpoint(BaseModel):
    class CheckpointType(models.TextChoices):
        ENTRY = 'ENTRY', 'Entry Control Point'
        EXIT = 'EXIT', 'Exit Control Point'
        INSPECTION = 'INSPECTION', 'Inspection Point'
        TRAFFIC_CONTROL = 'TRAFFIC_CONTROL', 'Traffic Control Point'
        OTHER = 'OTHER', 'Other'

    name = models.CharField(max_length=150)
    checkpoint_type = models.CharField(max_length=20, choices=CheckpointType.choices, default=CheckpointType.OTHER)
    location = gis_models.PointField(geography=True, srid=4326)
    unit = models.ForeignKey(Unit, null=True, blank=True, on_delete=models.SET_NULL, related_name='checkpoints')
    is_operational = models.BooleanField(default=True)
    remarks = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=['checkpoint_type']), models.Index(fields=['unit'])]

    def __str__(self):
        return self.name


class LandingZone(BaseModel):
    class LZType(models.TextChoices):
        HELICOPTER = 'HELICOPTER', 'Helicopter LZ'
        FIXED_WING = 'FIXED_WING', 'Fixed-Wing Strip'
        DROP_ZONE = 'DROP_ZONE', 'Drop Zone'

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        INACTIVE = 'INACTIVE', 'Inactive'
        UNDER_SURVEY = 'UNDER_SURVEY', 'Under Survey'

    name = models.CharField(max_length=150)
    lz_type = models.CharField(max_length=20, choices=LZType.choices, default=LZType.HELICOPTER)
    location = gis_models.PointField(geography=True, srid=4326)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    unit = models.ForeignKey(Unit, null=True, blank=True, on_delete=models.SET_NULL, related_name='landing_zones')
    capacity = models.CharField(max_length=100, blank=True, help_text='e.g. "2x UH-1", "C-130 capable"')
    surface_type = models.CharField(max_length=100, blank=True)
    remarks = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=['lz_type']), models.Index(fields=['status'])]

    def __str__(self):
        return self.name


class MapHazard(BaseModel):
    """
    A geospatial hazard marker (minefield, IED, flooding, etc.) for the
    operational map — distinct from apps.missions.HazardAssessment
    (the probability/severity risk-assessment workflow record).
    """

    class HazardType(models.TextChoices):
        MINEFIELD = 'MINEFIELD', 'Minefield'
        IED = 'IED', 'IED / UXO'
        FLOODING = 'FLOODING', 'Flooding'
        LANDSLIDE = 'LANDSLIDE', 'Landslide'
        CIVIL_UNREST = 'CIVIL_UNREST', 'Civil Unrest'
        OTHER = 'OTHER', 'Other'

    class Severity(models.TextChoices):
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'

    name = models.CharField(max_length=150)
    hazard_type = models.CharField(max_length=20, choices=HazardType.choices, default=HazardType.OTHER)
    location = gis_models.PointField(geography=True, srid=4326)
    radius_meters = models.PositiveIntegerField(null=True, blank=True, help_text='Approximate affected radius.')
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.MEDIUM)
    reported_by = models.ForeignKey(
        Personnel, null=True, blank=True, on_delete=models.SET_NULL, related_name='reported_map_hazards',
    )
    reported_at = models.DateTimeField(null=True, blank=True)
    is_resolved = models.BooleanField(default=False)
    description = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=['hazard_type']), models.Index(fields=['severity', 'is_resolved'])]

    def __str__(self):
        return f'{self.name} ({self.get_hazard_type_display()})'


class Route(BaseModel):
    class RouteType(models.TextChoices):
        SUPPLY = 'SUPPLY', 'Main Supply Route'
        PATROL = 'PATROL', 'Patrol Route'
        EVACUATION = 'EVACUATION', 'Evacuation Route'
        OTHER = 'OTHER', 'Other'

    name = models.CharField(max_length=150)
    route_type = models.CharField(max_length=20, choices=RouteType.choices, default=RouteType.OTHER)
    path = gis_models.LineStringField(geography=True, srid=4326)
    unit = models.ForeignKey(Unit, null=True, blank=True, on_delete=models.SET_NULL, related_name='routes')
    description = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=['route_type']), models.Index(fields=['unit'])]

    def __str__(self):
        return self.name


class MapLayer(BaseModel):
    """
    Metadata describing a toggleable overlay layer on the operational map
    (drives the frontend's layer-visibility panel). The actual geometry
    lives in the models above; this just tracks which layer categories
    exist and their default visibility/styling.
    """

    class LayerType(models.TextChoices):
        AOR_BOUNDARIES = 'AOR_BOUNDARIES', 'AOR Boundaries'
        CHECKPOINTS = 'CHECKPOINTS', 'Checkpoints'
        LANDING_ZONES = 'LANDING_ZONES', 'Landing Zones'
        HAZARDS = 'HAZARDS', 'Hazards'
        ROUTES = 'ROUTES', 'Routes'
        MISSIONS = 'MISSIONS', 'Mission Locations'
        VEHICLES = 'VEHICLES', 'Vehicle Positions'
        CUSTOM = 'CUSTOM', 'Custom'

    name = models.CharField(max_length=100)
    layer_type = models.CharField(max_length=20, choices=LayerType.choices, unique=True)
    is_visible_by_default = models.BooleanField(default=True)
    color = models.CharField(max_length=20, default='#22d3ee')
    description = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        ordering = ['name']

    def __str__(self):
        return self.name
