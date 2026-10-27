from django.contrib.gis.db.models import Union as GeoUnion
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.aircraft.models import Aircraft
from apps.core.audit import log_action
from apps.core.models import AuditLog
from apps.core.permissions import ModulePermissionMixin, UnitScopedQuerysetMixin
from apps.core.rbac import Module
from apps.gis.utils import MGRSError, latlon_to_mgrs, mgrs_to_latlon
from apps.missions.models import Mission
from apps.personnel.models import Unit
from apps.vehicles.models import Vehicle

from .models import AORBoundary, Checkpoint, LandingZone, MapHazard, MapLayer, Route
from .serializers import (
    AORBoundarySerializer,
    CheckpointSerializer,
    LandingZoneSerializer,
    MapHazardSerializer,
    MapLayerSerializer,
    MGRSConvertSerializer,
    RouteSerializer,
    geometry_to_polygon_rings,
    linestring_to_coords,
    point_to_dict,
    polygon_to_coords,
)


class _AuditedGeoViewSet(ModulePermissionMixin, viewsets.ModelViewSet):
    """Shared CRUD + audit-log plumbing for the GIS reference-data ViewSets below."""

    permission_module = Module.GIS

    def perform_create(self, serializer):
        instance = serializer.save()
        log_action(
            user=self.request.user, action=AuditLog.Action.CREATE, instance=instance,
            description=f'Created {instance.__class__.__name__} "{instance.name}"', request=self.request,
        )

    def perform_update(self, serializer):
        instance = serializer.save()
        log_action(
            user=self.request.user, action=AuditLog.Action.UPDATE, instance=instance,
            description=f'Updated {instance.__class__.__name__} "{instance.name}"', request=self.request,
        )

    def perform_destroy(self, instance):
        log_action(
            user=self.request.user, action=AuditLog.Action.DELETE, instance=instance,
            description=f'Deactivated {instance.__class__.__name__} "{instance.name}"', request=self.request,
        )
        instance.is_active = False
        instance.save(update_fields=['is_active'])


class AORBoundaryViewSet(UnitScopedQuerysetMixin, _AuditedGeoViewSet):
    queryset = AORBoundary.objects.select_related('unit').all()
    serializer_class = AORBoundarySerializer
    filterset_fields = ['unit', 'is_active']
    search_fields = ['name']

    @action(detail=False, methods=['get'], url_path='consolidated')
    def consolidated(self, request):
        """
        GET /gis/aor-boundaries/consolidated/?unit=<unit_id>

        Returns the geometric union of every active AOR boundary belonging
        to `unit` and all of its subordinate units — i.e. a mother unit's
        consolidated AOR is the union of its Wings'/Groups'/Squadrons' AORs.
        A Squadron with no subordinates just gets its own boundary back
        unmodified (the union of one polygon is itself).
        """
        unit_id = request.query_params.get('unit')
        if not unit_id:
            raise ValidationError('The "unit" query parameter is required.')
        unit = get_object_or_404(Unit, pk=unit_id)

        descendant_ids = unit.get_descendant_ids(include_self=True)
        boundaries = self.get_queryset().filter(unit_id__in=descendant_ids, is_active=True)

        union_geometry = boundaries.aggregate(union=GeoUnion('boundary'))['union']

        return Response({
            'unit': unit.name,
            'unit_category': unit.category,
            'source_boundary_count': boundaries.count(),
            'source_units': list(boundaries.values_list('unit__name', flat=True).distinct()),
            'consolidated_boundary': geometry_to_polygon_rings(union_geometry),
        })


class CheckpointViewSet(UnitScopedQuerysetMixin, _AuditedGeoViewSet):
    queryset = Checkpoint.objects.select_related('unit').all()
    serializer_class = CheckpointSerializer
    filterset_fields = ['checkpoint_type', 'unit', 'is_operational', 'is_active']
    search_fields = ['name']


class LandingZoneViewSet(UnitScopedQuerysetMixin, _AuditedGeoViewSet):
    queryset = LandingZone.objects.select_related('unit').all()
    serializer_class = LandingZoneSerializer
    filterset_fields = ['lz_type', 'status', 'unit', 'is_active']
    search_fields = ['name']


class MapHazardViewSet(_AuditedGeoViewSet):
    """
    Not unit-scoped: hazards (minefields, IEDs, etc.) can affect any unit
    operating in the area regardless of who reported them, so every
    authenticated user with GIS view access sees the full hazard list.
    """

    queryset = MapHazard.objects.select_related('reported_by').all()
    serializer_class = MapHazardSerializer
    filterset_fields = ['hazard_type', 'severity', 'is_resolved', 'is_active']
    search_fields = ['name']


class RouteViewSet(UnitScopedQuerysetMixin, _AuditedGeoViewSet):
    queryset = Route.objects.select_related('unit').all()
    serializer_class = RouteSerializer
    filterset_fields = ['route_type', 'unit', 'is_active']
    search_fields = ['name']


class MapLayerViewSet(ModulePermissionMixin, viewsets.ModelViewSet):
    queryset = MapLayer.objects.all()
    serializer_class = MapLayerSerializer
    permission_module = Module.GIS


class OperationalOverlayView(APIView):
    """
    Aggregates every GIS layer plus live vehicle/mission/aircraft positions
    into one payload for the Operational Mapping screen — AOR boundaries,
    checkpoints, landing zones, hazards, routes, and unit positions, each
    with MGRS coordinates computed alongside lat/lng.

    Note: this aggregation endpoint is not yet unit-scoped — it currently
    returns all units' data to any authenticated viewer. Per-module
    ViewSets (AORBoundaryViewSet etc.) ARE unit-scoped; scoping this
    combined view the same way is a follow-up (it would need each of the
    six queries below filtered by request.user.unit_id individually).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        aor_boundaries = [
            {
                'id': str(b.id), 'name': b.name, 'unit': b.unit.name if b.unit else None,
                'color': b.color, 'coordinates': polygon_to_coords(b.boundary),
            }
            for b in AORBoundary.objects.filter(is_active=True).select_related('unit')
        ]

        checkpoints = [
            {
                'id': str(c.id), 'name': c.name, 'checkpoint_type': c.checkpoint_type,
                'is_operational': c.is_operational, **point_to_dict(c.location),
            }
            for c in Checkpoint.objects.filter(is_active=True)
        ]

        landing_zones = [
            {
                'id': str(lz.id), 'name': lz.name, 'lz_type': lz.lz_type, 'status': lz.status,
                **point_to_dict(lz.location),
            }
            for lz in LandingZone.objects.filter(is_active=True)
        ]

        hazards = [
            {
                'id': str(h.id), 'name': h.name, 'hazard_type': h.hazard_type, 'severity': h.severity,
                'radius_meters': h.radius_meters, **point_to_dict(h.location),
            }
            for h in MapHazard.objects.filter(is_active=True, is_resolved=False)
        ]

        routes = [
            {
                'id': str(r.id), 'name': r.name, 'route_type': r.route_type,
                'coordinates': linestring_to_coords(r.path),
            }
            for r in Route.objects.filter(is_active=True)
        ]

        vehicles = [
            {'id': str(v.id), 'label': v.plate_number, **point_to_dict(v.last_known_location)}
            for v in Vehicle.objects.filter(is_active=True).exclude(last_known_location__isnull=True)
        ]

        missions = [
            {'id': str(m.id), 'label': m.name, 'status': m.status, **point_to_dict(m.location)}
            for m in Mission.objects.filter(is_active=True).exclude(location__isnull=True)
        ]

        aircraft_bases = [
            {
                'id': str(a.id), 'label': a.tail_number, 'flying_status': a.flying_status,
                'unit': a.base_unit.name if a.base_unit else None,
            }
            for a in Aircraft.objects.filter(is_active=True)
        ]

        layers = MapLayerSerializer(MapLayer.objects.all(), many=True).data

        return Response({
            'generated_at': timezone.now(),
            'layers': layers,
            'aor_boundaries': aor_boundaries,
            'checkpoints': checkpoints,
            'landing_zones': landing_zones,
            'hazards': hazards,
            'routes': routes,
            'vehicles': vehicles,
            'missions': missions,
            'aircraft': aircraft_bases,
        })


class MGRSConvertView(APIView):
    """Ad-hoc lat/lng -> MGRS conversion utility: GET /gis/mgrs-convert/?lat=..&lng=.."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = MGRSConvertSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        lat = serializer.validated_data['lat']
        lng = serializer.validated_data['lng']
        return Response({'lat': lat, 'lng': lng, 'mgrs': latlon_to_mgrs(lat, lng)})


class MGRSParseView(APIView):
    """MGRS -> lat/lng: GET /gis/mgrs-parse/?mgrs=51P+XQ+81324+37990 (answers 400 with a readable message when invalid)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            lat, lng = mgrs_to_latlon(request.query_params.get('mgrs', ''))
        except MGRSError as exc:
            return Response({'mgrs': [str(exc)]}, status=400)
        return Response({'lat': lat, 'lng': lng, 'mgrs': latlon_to_mgrs(lat, lng)})
