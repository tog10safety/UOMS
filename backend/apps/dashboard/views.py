from django.contrib.gis.geos import GEOSGeometry
from django.db.models import Case, Count, IntegerField, When
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.aircraft.models import Aircraft
from apps.core.models import AuditLog
from apps.core.permissions import HasModulePermission
from apps.core.rbac import Action, Module
from apps.missions.models import Mission
from apps.personnel.models import Personnel
from apps.risk.models import RiskAlert
from apps.vehicles.models import Vehicle


class DashboardSummaryView(APIView):
    """
    Single aggregation endpoint powering the main Dashboard screen:
    operational status, personnel summary, vehicle status, aircraft flying
    status, mission status, risk alerts, recent activity, and map overview
    points — so the React dashboard can render everything from one call.
    """

    permission_classes = [HasModulePermission]
    permission_module = Module.DASHBOARD
    required_action = Action.VIEW

    def get(self, request):
        personnel_qs = Personnel.objects.filter(is_active=True)
        personnel_by_status = {
            row['status']: row['count']
            for row in personnel_qs.values('status').annotate(count=Count('id')).order_by()
        }

        vehicle_qs = Vehicle.objects.filter(is_active=True)
        vehicle_by_status = {
            row['status']: row['count']
            for row in vehicle_qs.values('status').annotate(count=Count('id')).order_by()
        }

        aircraft_qs = Aircraft.objects.filter(is_active=True)
        aircraft_by_status = {
            row['flying_status']: row['count']
            for row in aircraft_qs.values('flying_status').annotate(count=Count('id')).order_by()
        }

        mission_qs = Mission.objects.filter(is_active=True)
        mission_by_status = {
            row['status']: row['count']
            for row in mission_qs.values('status').annotate(count=Count('id')).order_by()
        }

        active_alerts = RiskAlert.objects.filter(is_resolved=False, is_active=True).select_related('mission')
        severity_rank = Case(
            When(severity=RiskAlert.Severity.CRITICAL, then=4),
            When(severity=RiskAlert.Severity.HIGH, then=3),
            When(severity=RiskAlert.Severity.MEDIUM, then=2),
            When(severity=RiskAlert.Severity.LOW, then=1),
            default=0,
            output_field=IntegerField(),
        )
        alerts_payload = [
            {
                'id': str(alert.id),
                'title': alert.title,
                'severity': alert.severity,
                'mission': alert.mission.name if alert.mission else None,
                'created_at': alert.created_at,
            }
            for alert in active_alerts.annotate(_severity_rank=severity_rank).order_by('-_severity_rank', '-created_at')[:10]
        ]

        recent_activity = [
            {
                'id': log.id,
                'user': log.user.username if log.user else 'system',
                'action': log.action,
                'model_name': log.model_name,
                'description': log.description,
                'created_at': log.created_at,
            }
            for log in AuditLog.objects.select_related('user').order_by('-created_at')[:15]
        ]

        map_points = []
        for vehicle in vehicle_qs.exclude(last_known_location__isnull=True):
            map_points.append(_geo_point('vehicle', vehicle.plate_number, vehicle.last_known_location))
        for mission in mission_qs.exclude(location__isnull=True):
            map_points.append(_geo_point('mission', mission.name, mission.location))

        return Response({
            'generated_at': timezone.now(),
            'operational_status': {
                'total_personnel': personnel_qs.count(),
                'total_vehicles': vehicle_qs.count(),
                'total_aircraft': aircraft_qs.count(),
                'active_missions': mission_qs.exclude(status__in=['COMPLETED', 'CANCELLED']).count(),
                'open_risk_alerts': active_alerts.count(),
            },
            'personnel_summary': {
                'total': personnel_qs.count(),
                'by_status': personnel_by_status,
            },
            'vehicle_status': {
                'total': vehicle_qs.count(),
                'by_status': vehicle_by_status,
            },
            'aircraft_flying_status': {
                'total': aircraft_qs.count(),
                'by_status': aircraft_by_status,
            },
            'mission_status': {
                'total': mission_qs.count(),
                'by_status': mission_by_status,
            },
            'risk_alerts': alerts_payload,
            'recent_activities': recent_activity,
            'map_overview': map_points,
        })



def _geo_point(entity_type, label, geom: GEOSGeometry):
    return {
        'type': entity_type,
        'label': label,
        'lat': geom.y,
        'lng': geom.x,
    }
