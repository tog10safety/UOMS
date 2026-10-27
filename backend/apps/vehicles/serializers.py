from django.contrib.gis.geos import Point
from rest_framework import serializers

from .models import Trip, Vehicle, VehicleLocationUpdate, VehicleMaintenanceRecord


class PointFieldMixin:
    """Represents a PostGIS PointField as a simple {lat, lng} pair over the API."""

    def point_to_repr(self, point):
        if point is None:
            return None
        return {'lat': point.y, 'lng': point.x}

    def repr_to_point(self, data):
        if not data:
            return None
        return Point(float(data['lng']), float(data['lat']), srid=4326)


class VehicleListSerializer(serializers.ModelSerializer, PointFieldMixin):
    driver_name = serializers.CharField(source='assigned_driver.full_name', read_only=True, default=None)
    mission_name = serializers.CharField(source='assigned_mission.name', read_only=True, default=None)
    last_known_location = serializers.SerializerMethodField()

    class Meta:
        model = Vehicle
        fields = [
            'id', 'plate_number', 'vehicle_type', 'make', 'model', 'status',
            'driver_name', 'mission_name', 'odometer_km', 'last_known_location',
            'last_location_updated_at', 'is_active',
        ]

    def get_last_known_location(self, obj):
        return self.point_to_repr(obj.last_known_location)


class VehicleDetailSerializer(serializers.ModelSerializer, PointFieldMixin):
    last_known_location = serializers.SerializerMethodField()

    class Meta:
        model = Vehicle
        fields = [
            'id', 'plate_number', 'make', 'model', 'vehicle_type', 'year', 'capacity',
            'fuel_type', 'odometer_km', 'status', 'assigned_driver', 'assigned_mission',
            'last_known_location', 'last_location_updated_at', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'last_known_location', 'last_location_updated_at', 'created_at', 'updated_at']

    def get_last_known_location(self, obj):
        return self.point_to_repr(obj.last_known_location)


class VehicleLocationUpdateSerializer(serializers.ModelSerializer, PointFieldMixin):
    location = serializers.DictField(write_only=True, help_text='{"lat": <float>, "lng": <float>}')
    location_display = serializers.SerializerMethodField()

    class Meta:
        model = VehicleLocationUpdate
        fields = ['id', 'vehicle', 'location', 'location_display', 'speed_kph', 'heading_degrees', 'recorded_at']
        read_only_fields = ['id']

    def get_location_display(self, obj):
        return self.point_to_repr(obj.location)

    def validate_location(self, value):
        if 'lat' not in value or 'lng' not in value:
            raise serializers.ValidationError('location must include "lat" and "lng".')
        return value

    def create(self, validated_data):
        loc = validated_data.pop('location')
        validated_data['location'] = self.repr_to_point(loc)
        return super().create(validated_data)


class TripSerializer(serializers.ModelSerializer):
    vehicle_plate = serializers.CharField(source='vehicle.plate_number', read_only=True)
    driver_name = serializers.CharField(source='driver.full_name', read_only=True)
    distance_km = serializers.IntegerField(read_only=True)

    class Meta:
        model = Trip
        fields = [
            'id', 'vehicle', 'vehicle_plate', 'driver', 'driver_name', 'mission',
            'origin', 'destination', 'purpose', 'status', 'start_time', 'end_time',
            'start_odometer_km', 'end_odometer_km', 'distance_km', 'remarks',
            'is_active', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def validate(self, attrs):
        end_odo = attrs.get('end_odometer_km', getattr(self.instance, 'end_odometer_km', None))
        start_odo = attrs.get('start_odometer_km', getattr(self.instance, 'start_odometer_km', None))
        if end_odo is not None and start_odo is not None and end_odo < start_odo:
            raise serializers.ValidationError('end_odometer_km cannot be less than start_odometer_km.')
        return attrs


class VehicleMaintenanceRecordSerializer(serializers.ModelSerializer):
    vehicle_plate = serializers.CharField(source='vehicle.plate_number', read_only=True)

    class Meta:
        model = VehicleMaintenanceRecord
        fields = [
            'id', 'vehicle', 'vehicle_plate', 'maintenance_type', 'description',
            'performed_by', 'cost', 'service_date', 'next_due_date',
            'odometer_at_service_km', 'is_active', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']
