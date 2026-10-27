from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.audit import log_action
from apps.core.models import AuditLog
from apps.core.permissions import ModulePermissionMixin, UnitScopedQuerysetMixin
from apps.core.rbac import Action, Module

from .models import Trip, Vehicle, VehicleLocationUpdate, VehicleMaintenanceRecord
from .serializers import (
    TripSerializer,
    VehicleDetailSerializer,
    VehicleListSerializer,
    VehicleLocationUpdateSerializer,
    VehicleMaintenanceRecordSerializer,
)


class VehicleViewSet(ModulePermissionMixin, UnitScopedQuerysetMixin, viewsets.ModelViewSet):
    """Vehicle registry with status, driver/mission assignment, and location tracking."""

    queryset = Vehicle.objects.select_related(
        'assigned_driver', 'assigned_mission'
    ).all()
    permission_module = Module.VEHICLES
    action_permission_map = {
        'report_location': Action.EDIT,
        'location_history': Action.VIEW,
        'dispatch_vehicle': Action.DISPATCH,
        'return_vehicle': Action.RETURN,
    }
    filterset_fields = [
        'status',
        'vehicle_type',
        'assigned_driver',
        'assigned_mission',
        'is_active',
    ]
    search_fields = ['plate_number', 'make', 'model']
    ordering_fields = ['plate_number', 'created_at', 'status']

    def get_serializer_class(self):
        if self.action == 'list':
            return VehicleListSerializer
        return VehicleDetailSerializer

    def perform_create(self, serializer):
        instance = serializer.save()
        log_action(
            user=self.request.user, action=AuditLog.Action.CREATE, instance=instance,
            description=f'Registered vehicle {instance.plate_number}', request=self.request,
        )

    def perform_update(self, serializer):
        instance = serializer.save()
        log_action(
            user=self.request.user, action=AuditLog.Action.UPDATE, instance=instance,
            description=f'Updated vehicle {instance.plate_number}', request=self.request,
        )

    def perform_destroy(self, instance):
        log_action(
            user=self.request.user, action=AuditLog.Action.DELETE, instance=instance,
            description=f'Deactivated vehicle {instance.plate_number}', request=self.request,
        )
        instance.is_active = False
        instance.save(update_fields=['is_active'])

    @action(detail=True, methods=['post'], url_path='location')
    def report_location(self, request, pk=None):
        """
        Push a new location/status update for this vehicle. Body:
        {"location": {"lat": ..., "lng": ...}, "speed_kph": ..., "heading_degrees": ...}
        Updates both the location-history trail and the vehicle's last-known-location.
        """
        vehicle = self.get_object()
        serializer = VehicleLocationUpdateSerializer(
            data={**request.data, 'vehicle': vehicle.id, 'recorded_at': timezone.now()},
        )
        serializer.is_valid(raise_exception=True)
        location_update = serializer.save()

        vehicle.last_known_location = location_update.location
        vehicle.last_location_updated_at = location_update.recorded_at
        vehicle.save(update_fields=['last_known_location', 'last_location_updated_at'])

        return Response(VehicleLocationUpdateSerializer(location_update).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='location-history')
    def location_history(self, request, pk=None):
        vehicle = self.get_object()
        history = vehicle.location_history.all()[:200]
        return Response(VehicleLocationUpdateSerializer(history, many=True).data)

    @action(detail=True, methods=['post'], url_path='dispatch')
    def dispatch_vehicle(self, request, pk=None):
        """
        AVAILABLE -> ON_MISSION. Body: {"mission": "<mission-id>"} (optional).
        Rejects dispatch of a vehicle that isn't currently AVAILABLE — the
        backend enforces this status rule regardless of what the frontend allows.
        """
        vehicle = self.get_object()
        if vehicle.status != Vehicle.Status.AVAILABLE:
            raise ValidationError(f'Cannot dispatch a vehicle with status "{vehicle.status}" — must be AVAILABLE.')

        mission_id = request.data.get('mission')
        vehicle.status = Vehicle.Status.ON_MISSION
        if mission_id:
            vehicle.assigned_mission_id = mission_id
        vehicle.save(update_fields=['status', 'assigned_mission'])

        log_action(
            user=request.user, action=AuditLog.Action.OTHER, instance=vehicle,
            description=f'Dispatched vehicle {vehicle.plate_number}', request=request,
        )
        return Response(VehicleDetailSerializer(vehicle).data)

    @action(detail=True, methods=['post'], url_path='return')
    def return_vehicle(self, request, pk=None):
        """ON_MISSION -> AVAILABLE."""
        vehicle = self.get_object()
        if vehicle.status != Vehicle.Status.ON_MISSION:
            raise ValidationError(f'Cannot return a vehicle with status "{vehicle.status}" — must be ON_MISSION.')

        vehicle.status = Vehicle.Status.AVAILABLE
        vehicle.assigned_mission = None
        vehicle.save(update_fields=['status', 'assigned_mission'])

        log_action(
            user=request.user, action=AuditLog.Action.OTHER, instance=vehicle,
            description=f'Returned vehicle {vehicle.plate_number}', request=request,
        )
        return Response(VehicleDetailSerializer(vehicle).data)


class TripViewSet(ModulePermissionMixin, viewsets.ModelViewSet):
    """Trip history — dispatch records for vehicles."""

    queryset = Trip.objects.select_related('vehicle', 'driver', 'mission').all()
    serializer_class = TripSerializer
    permission_module = Module.VEHICLES
    filterset_fields = ['vehicle', 'driver', 'mission', 'status']
    ordering_fields = ['start_time', 'created_at']

    def perform_create(self, serializer):
        instance = serializer.save()
        log_action(
            user=self.request.user, action=AuditLog.Action.CREATE, instance=instance,
            description=f'Logged trip for {instance.vehicle.plate_number}', request=self.request,
        )

    def perform_update(self, serializer):
        instance = serializer.save()
        log_action(
            user=self.request.user, action=AuditLog.Action.UPDATE, instance=instance,
            description=f'Updated trip for {instance.vehicle.plate_number}', request=self.request,
        )


class VehicleMaintenanceRecordViewSet(ModulePermissionMixin, viewsets.ModelViewSet):
    """Maintenance records for vehicles."""

    queryset = VehicleMaintenanceRecord.objects.select_related('vehicle').all()
    serializer_class = VehicleMaintenanceRecordSerializer
    permission_module = Module.VEHICLES
    filterset_fields = ['vehicle', 'maintenance_type']
    ordering_fields = ['service_date', 'created_at']

    def perform_create(self, serializer):
        instance = serializer.save()
        vehicle = instance.vehicle
        if instance.maintenance_type in (
            VehicleMaintenanceRecord.MaintenanceType.REPAIR,
            VehicleMaintenanceRecord.MaintenanceType.PREVENTIVE,
        ) and vehicle.status == Vehicle.Status.AVAILABLE:
            vehicle.status = Vehicle.Status.MAINTENANCE
            vehicle.save(update_fields=['status'])

        log_action(
            user=self.request.user, action=AuditLog.Action.CREATE, instance=instance,
            description=f'Logged maintenance for {instance.vehicle.plate_number}', request=self.request,
        )
