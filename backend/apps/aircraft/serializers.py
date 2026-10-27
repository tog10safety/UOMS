from django.contrib.gis.geos import Point
from rest_framework import serializers

from .models import Aircraft, Flight, FlightCrewAssignment, FlightWaypoint


def point_to_repr(point):
    if point is None:
        return None
    return {'lat': point.y, 'lng': point.x}


def repr_to_point(data):
    if not data:
        return None
    return Point(float(data['lng']), float(data['lat']), srid=4326)


class AircraftSerializer(serializers.ModelSerializer):
    base_unit_name = serializers.CharField(source='base_unit.name', read_only=True, default=None)

    class Meta:
        model = Aircraft
        fields = [
            'id', 'tail_number', 'aircraft_type', 'manufacturer', 'model', 'capacity',
            'flying_status', 'base_unit', 'base_unit_name', 'is_active', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class FlightCrewAssignmentSerializer(serializers.ModelSerializer):
    personnel_name = serializers.CharField(source='personnel.full_name', read_only=True)

    class Meta:
        model = FlightCrewAssignment
        fields = ['id', 'flight', 'personnel', 'personnel_name', 'crew_role']
        read_only_fields = ['id']


class FlightWaypointSerializer(serializers.ModelSerializer):
    location = serializers.SerializerMethodField()
    location_input = serializers.DictField(write_only=True, required=False, source='location')

    class Meta:
        model = FlightWaypoint
        fields = ['id', 'flight', 'sequence', 'name', 'location', 'location_input', 'eta', 'notes']
        read_only_fields = ['id']

    def get_location(self, obj):
        return point_to_repr(obj.location)

    def validate_location_input(self, value):
        return repr_to_point(value)


class FlightListSerializer(serializers.ModelSerializer):
    aircraft_tail_number = serializers.CharField(source='aircraft.tail_number', read_only=True)
    mission_name = serializers.CharField(source='mission.name', read_only=True, default=None)
    unit_name = serializers.CharField(source='unit.name', read_only=True, default=None)

    class Meta:
        model = Flight
        fields = [
            'id', 'flight_number', 'aircraft', 'aircraft_tail_number', 'mission', 'mission_name',
            'unit', 'unit_name', 'origin', 'destination', 'scheduled_departure', 'scheduled_arrival',
            'actual_departure', 'actual_arrival', 'status',
        ]


class FlightDetailSerializer(serializers.ModelSerializer):
    origin_location = serializers.SerializerMethodField()
    destination_location = serializers.SerializerMethodField()
    crew_assignments = FlightCrewAssignmentSerializer(many=True, read_only=True)
    waypoints = FlightWaypointSerializer(many=True, read_only=True)

    class Meta:
        model = Flight
        fields = [
            'id', 'flight_number', 'aircraft', 'mission', 'unit',
            'origin', 'origin_location', 'destination', 'destination_location',
            'scheduled_departure', 'scheduled_arrival', 'actual_departure', 'actual_arrival',
            'status', 'caap_flight_plan_number', 'caap_aircraft_registration', 'caap_remarks',
            'crew_assignments', 'waypoints', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_origin_location(self, obj):
        return point_to_repr(obj.origin_location)

    def get_destination_location(self, obj):
        return point_to_repr(obj.destination_location)

    def validate(self, attrs):
        departure = attrs.get('scheduled_departure', getattr(self.instance, 'scheduled_departure', None))
        arrival = attrs.get('scheduled_arrival', getattr(self.instance, 'scheduled_arrival', None))
        if departure and arrival and arrival <= departure:
            raise serializers.ValidationError('scheduled_arrival must be after scheduled_departure.')
        return attrs
