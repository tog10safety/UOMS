from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.audit import log_action
from apps.core.models import AuditLog
from apps.core.permissions import ModulePermissionMixin, UnitScopedQuerysetMixin
from apps.core.rbac import Action, Module

from .models import Aircraft, Flight, FlightCrewAssignment, FlightWaypoint
from .serializers import (
    AircraftSerializer,
    FlightCrewAssignmentSerializer,
    FlightDetailSerializer,
    FlightListSerializer,
    FlightWaypointSerializer,
)


class AircraftViewSet(ModulePermissionMixin, UnitScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Aircraft.objects.select_related('base_unit').all()
    serializer_class = AircraftSerializer
    permission_module = Module.AIRCRAFT
    unit_field = 'base_unit'
    filterset_fields = ['flying_status', 'base_unit', 'is_active']
    search_fields = ['tail_number', 'aircraft_type', 'manufacturer']
    ordering_fields = ['tail_number', 'created_at']

    def perform_create(self, serializer):
        instance = serializer.save()
        log_action(
            user=self.request.user, action=AuditLog.Action.CREATE, instance=instance,
            description=f'Registered aircraft {instance.tail_number}', request=self.request,
        )

    def perform_update(self, serializer):
        instance = serializer.save()
        log_action(
            user=self.request.user, action=AuditLog.Action.UPDATE, instance=instance,
            description=f'Updated aircraft {instance.tail_number}', request=self.request,
        )

    def perform_destroy(self, instance):
        log_action(
            user=self.request.user, action=AuditLog.Action.DELETE, instance=instance,
            description=f'Deactivated aircraft {instance.tail_number}', request=self.request,
        )
        instance.is_active = False
        instance.save(update_fields=['is_active'])


class FlightViewSet(ModulePermissionMixin, UnitScopedQuerysetMixin, viewsets.ModelViewSet):
    """
    Flight scheduling and departure/arrival monitoring.

    AOR unit visibility is enforced by UnitScopedQuerysetMixin: a user's
    unit determines which flights they see, unless their role grants
    cross-AOR visibility (ADMIN/COMMANDER).
    """

    queryset = Flight.objects.select_related('aircraft', 'mission', 'unit').prefetch_related(
        'crew_assignments__personnel', 'waypoints'
    )
    permission_module = Module.AIRCRAFT
    action_permission_map = {
        'mark_departed': Action.DISPATCH,
        'mark_arrived': Action.RETURN,
    }
    filterset_fields = ['status', 'aircraft', 'mission', 'unit']
    search_fields = ['flight_number', 'origin', 'destination', 'caap_flight_plan_number']
    ordering_fields = ['scheduled_departure', 'created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return FlightListSerializer
        return FlightDetailSerializer

    def perform_create(self, serializer):
        instance = serializer.save()
        log_action(
            user=self.request.user, action=AuditLog.Action.CREATE, instance=instance,
            description=f'Scheduled flight {instance.flight_number}', request=self.request,
        )

    def perform_update(self, serializer):
        instance = serializer.save()
        log_action(
            user=self.request.user, action=AuditLog.Action.UPDATE, instance=instance,
            description=f'Updated flight {instance.flight_number}', request=self.request,
        )

    def perform_destroy(self, instance):
        log_action(
            user=self.request.user, action=AuditLog.Action.DELETE, instance=instance,
            description=f'Cancelled flight {instance.flight_number}', request=self.request,
        )
        instance.is_active = False
        instance.status = Flight.Status.CANCELLED
        instance.save(update_fields=['is_active', 'status'])

    @action(detail=True, methods=['post'], url_path='depart')
    def mark_departed(self, request, pk=None):
        """Records actual departure time and transitions status to DEPARTED."""
        flight = self.get_object()
        flight.actual_departure = request.data.get('actual_departure') or timezone.now()
        flight.status = Flight.Status.DEPARTED
        flight.save(update_fields=['actual_departure', 'status'])

        flight.aircraft.flying_status = Aircraft.FlyingStatus.IN_FLIGHT
        flight.aircraft.save(update_fields=['flying_status'])

        log_action(
            user=request.user, action=AuditLog.Action.UPDATE, instance=flight,
            description=f'Flight {flight.flight_number} marked as departed', request=request,
        )
        return Response(FlightDetailSerializer(flight).data)

    @action(detail=True, methods=['post'], url_path='arrive')
    def mark_arrived(self, request, pk=None):
        """Records actual arrival time and transitions status to ARRIVED."""
        flight = self.get_object()
        flight.actual_arrival = request.data.get('actual_arrival') or timezone.now()
        flight.status = Flight.Status.ARRIVED
        flight.save(update_fields=['actual_arrival', 'status'])

        flight.aircraft.flying_status = Aircraft.FlyingStatus.GROUNDED
        flight.aircraft.save(update_fields=['flying_status'])

        log_action(
            user=request.user, action=AuditLog.Action.UPDATE, instance=flight,
            description=f'Flight {flight.flight_number} marked as arrived', request=request,
        )
        return Response(FlightDetailSerializer(flight).data)

    @action(detail=True, methods=['get', 'post'], url_path='crew')
    def crew(self, request, pk=None):
        flight = self.get_object()
        if request.method == 'GET':
            return Response(FlightCrewAssignmentSerializer(flight.crew_assignments.all(), many=True).data)

        serializer = FlightCrewAssignmentSerializer(data={**request.data, 'flight': flight.id})
        serializer.is_valid(raise_exception=True)
        crew_member = serializer.save()
        log_action(
            user=request.user, action=AuditLog.Action.CREATE, instance=crew_member,
            description=f'Assigned {crew_member.personnel.full_name} to flight {flight.flight_number}',
            request=request,
        )
        return Response(FlightCrewAssignmentSerializer(crew_member).data, status=201)

    @action(detail=True, methods=['get', 'post'], url_path='waypoints')
    def waypoints(self, request, pk=None):
        flight = self.get_object()
        if request.method == 'GET':
            return Response(FlightWaypointSerializer(flight.waypoints.all(), many=True).data)

        serializer = FlightWaypointSerializer(data={**request.data, 'flight': flight.id})
        serializer.is_valid(raise_exception=True)
        waypoint = serializer.save()
        return Response(FlightWaypointSerializer(waypoint).data, status=201)


class FlightCrewAssignmentViewSet(ModulePermissionMixin, viewsets.ModelViewSet):
    """Direct CRUD for crew assignments (in addition to the nested /flights/{id}/crew/ action)."""

    queryset = FlightCrewAssignment.objects.select_related('flight', 'personnel').all()
    serializer_class = FlightCrewAssignmentSerializer
    permission_module = Module.AIRCRAFT
    action_permission_map = {'create': Action.ASSIGN}
    filterset_fields = ['flight', 'personnel', 'crew_role']
