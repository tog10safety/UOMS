from django.contrib.gis.geos import LineString, Point, Polygon
from rest_framework import serializers

from apps.gis.utils import latlon_to_mgrs

from .models import AORBoundary, Checkpoint, LandingZone, MapHazard, MapLayer, Route


def point_to_dict(point):
    if point is None:
        return None
    return {'lat': point.y, 'lng': point.x, 'mgrs': latlon_to_mgrs(point.y, point.x)}


def dict_to_point(data):
    if not data:
        return None
    return Point(float(data['lng']), float(data['lat']), srid=4326)


def polygon_to_coords(polygon):
    if polygon is None:
        return None
    ring = polygon.coords[0]
    return [{'lat': lat, 'lng': lon} for lon, lat in ring]


def geometry_to_polygon_rings(geometry):
    """
    Converts a Polygon OR MultiPolygon (e.g. the result of a PostGIS union
    of several AOR boundaries that don't all touch) into a list of rings,
    each a list of {lat, lng} points — so the frontend can render one or
    several disjoint polygons uniformly.
    """
    if geometry is None:
        return []
    if geometry.geom_type == 'Polygon':
        return [polygon_to_coords(geometry)]
    if geometry.geom_type == 'MultiPolygon':
        return [polygon_to_coords(poly) for poly in geometry]
    return []


def coords_to_polygon(coords):
    if not coords:
        return None
    ring = [(float(c['lng']), float(c['lat'])) for c in coords]
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return Polygon(ring, srid=4326)


def linestring_to_coords(line):
    if line is None:
        return None
    return [{'lat': lat, 'lng': lon} for lon, lat in line.coords]


def coords_to_linestring(coords):
    if not coords:
        return None
    return LineString([(float(c['lng']), float(c['lat'])) for c in coords], srid=4326)


class AORBoundarySerializer(serializers.ModelSerializer):
    unit_name = serializers.CharField(source='unit.name', read_only=True, default=None)
    boundary = serializers.SerializerMethodField()
    boundary_input = serializers.ListField(write_only=True, required=False, source='boundary')

    class Meta:
        model = AORBoundary
        fields = [
            'id', 'name', 'unit', 'unit_name', 'boundary', 'boundary_input',
            'color', 'description', 'is_active', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_boundary(self, obj):
        return polygon_to_coords(obj.boundary)

    def validate_boundary_input(self, value):
        polygon = coords_to_polygon(value)
        if polygon is None:
            raise serializers.ValidationError('boundary_input must be a non-empty list of {lat, lng} points.')
        return polygon


class CheckpointSerializer(serializers.ModelSerializer):
    unit_name = serializers.CharField(source='unit.name', read_only=True, default=None)
    location = serializers.SerializerMethodField()
    location_input = serializers.DictField(write_only=True, required=False, source='location')

    class Meta:
        model = Checkpoint
        fields = [
            'id', 'name', 'checkpoint_type', 'location', 'location_input', 'unit', 'unit_name',
            'is_operational', 'remarks', 'is_active', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_location(self, obj):
        return point_to_dict(obj.location)

    def validate_location_input(self, value):
        return dict_to_point(value)


class LandingZoneSerializer(serializers.ModelSerializer):
    unit_name = serializers.CharField(source='unit.name', read_only=True, default=None)
    location = serializers.SerializerMethodField()
    location_input = serializers.DictField(write_only=True, required=False, source='location')

    class Meta:
        model = LandingZone
        fields = [
            'id', 'name', 'lz_type', 'location', 'location_input', 'status', 'unit', 'unit_name',
            'capacity', 'surface_type', 'remarks', 'is_active', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_location(self, obj):
        return point_to_dict(obj.location)

    def validate_location_input(self, value):
        return dict_to_point(value)


class MapHazardSerializer(serializers.ModelSerializer):
    reported_by_name = serializers.CharField(source='reported_by.full_name', read_only=True, default=None)
    location = serializers.SerializerMethodField()
    location_input = serializers.DictField(write_only=True, required=False, source='location')

    class Meta:
        model = MapHazard
        fields = [
            'id', 'name', 'hazard_type', 'location', 'location_input', 'radius_meters', 'severity',
            'reported_by', 'reported_by_name', 'reported_at', 'is_resolved', 'description',
            'is_active', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_location(self, obj):
        return point_to_dict(obj.location)

    def validate_location_input(self, value):
        return dict_to_point(value)


class RouteSerializer(serializers.ModelSerializer):
    unit_name = serializers.CharField(source='unit.name', read_only=True, default=None)
    path = serializers.SerializerMethodField()
    path_input = serializers.ListField(write_only=True, required=False, source='path')

    class Meta:
        model = Route
        fields = [
            'id', 'name', 'route_type', 'path', 'path_input', 'unit', 'unit_name',
            'description', 'is_active', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_path(self, obj):
        return linestring_to_coords(obj.path)

    def validate_path_input(self, value):
        line = coords_to_linestring(value)
        if line is None or len(value) < 2:
            raise serializers.ValidationError('path_input must be a list of at least 2 {lat, lng} points.')
        return line


class MapLayerSerializer(serializers.ModelSerializer):
    class Meta:
        model = MapLayer
        fields = ['id', 'name', 'layer_type', 'is_visible_by_default', 'color', 'description', 'is_active']
        read_only_fields = ['id']


class MGRSConvertSerializer(serializers.Serializer):
    """Query params for the ad-hoc /gis/mgrs-convert/ utility endpoint."""

    lat = serializers.FloatField()
    lng = serializers.FloatField()
