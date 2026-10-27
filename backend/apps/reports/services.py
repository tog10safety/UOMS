"""
Report data services.

Each function returns (title, headers, rows) where `rows` is a list of
lists matching `headers`, in the exact order/shape used for both the
on-screen report view and the PDF/Excel export — one source of truth
for a report's content.
"""
from apps.aircraft.models import Flight
from apps.inventory.models import InventoryItem
from apps.missions.models import HazardAssessment, Mission
from apps.personnel.models import Personnel
from apps.vehicles.models import Vehicle


def personnel_report():
    title = 'Personnel Report'
    headers = ['Service #', 'Name', 'Rank', 'Unit', 'Position', 'Status']
    rows = [
        [
            p.service_number, p.full_name, p.rank.abbreviation, p.unit.name,
            p.position.title if p.position else '—', p.get_status_display(),
        ]
        for p in Personnel.objects.filter(is_active=True).select_related('rank', 'unit', 'position').order_by('last_name')
    ]
    return title, headers, rows


def vehicle_report():
    title = 'Vehicle Status Report'
    headers = ['Plate #', 'Type', 'Status', 'Driver', 'Odometer (km)', 'Last Location Update']
    rows = [
        [
            v.plate_number, v.vehicle_type or '—', v.get_status_display(),
            v.assigned_driver.full_name if v.assigned_driver else '—', v.odometer_km,
            v.last_location_updated_at.strftime('%Y-%m-%d %H:%M') if v.last_location_updated_at else '—',
        ]
        for v in Vehicle.objects.filter(is_active=True).select_related('assigned_driver').order_by('plate_number')
    ]
    return title, headers, rows


def flight_report():
    title = 'Flight Report'
    headers = ['Flight #', 'Aircraft', 'Route', 'Scheduled Departure', 'Status', 'Mission']
    rows = [
        [
            f.flight_number, f.aircraft.tail_number, f'{f.origin} -> {f.destination}',
            f.scheduled_departure.strftime('%Y-%m-%d %H:%M'), f.get_status_display(),
            f.mission.name if f.mission else '—',
        ]
        for f in Flight.objects.filter(is_active=True).select_related('aircraft', 'mission').order_by('-scheduled_departure')
    ]
    return title, headers, rows


def mission_report():
    title = 'Mission Report'
    headers = ['Mission', 'Unit', 'Status', 'Risk Review', 'Overall Risk', 'Start Date']
    rows = [
        [
            m.name, m.unit.name if m.unit else '—', m.get_status_display(), m.effective_risk_review_status_display,
            (m.overall_risk_level or '—').replace('_', ' ').title(),
            m.start_date.strftime('%Y-%m-%d') if m.start_date else '—',
        ]
        for m in Mission.objects.filter(is_active=True).select_related('unit').order_by('-created_at')
    ]
    return title, headers, rows


def risk_report():
    """
    Mission risk register. MRM forms are authoritative: their hazards (as frozen on each form) are listed first;
    legacy quick assessments appear only for missions that have no MRM form.
    """
    from apps.mrm import risk as mrm_risk
    from apps.mrm.models import MissionHazard

    title = 'Mission Risk Report'
    headers = ['Source', 'Mission / Activity', 'Hazard', 'Category', 'Initial Risk', 'Residual Risk']
    rows = []

    def tier(rating):
        return f'{mrm_risk.level(rating).title()} ({rating})'

    lines = (
        MissionHazard.objects.filter(mrm__is_active=True)
        .select_related('mrm', 'mrm__mission', 'hazard')
        .order_by('-mrm__created_at', 'position')
    )
    for mh in lines:
        snap = mh.snapshot or {}
        rows.append([
            f'MRM {mh.mrm.mrm_number}',
            mh.mrm.mission.name if mh.mrm.mission_id else mh.mrm.activity_mission,
            (snap.get('hazard_description') or mh.hazard.hazard_description)[:80],
            snap.get('activity_code') or mh.hazard.activity_code,
            tier(snap.get('before_risk_rating') or mh.hazard.before_risk_rating),
            tier(mh.effective_residual_rating),
        ])

    mrm_mission_ids = set(
        MissionHazard.objects.filter(mrm__is_active=True, mrm__mission__isnull=False).values_list('mrm__mission_id', flat=True)
    )
    legacy = HazardAssessment.objects.filter(is_active=True).exclude(mission_id__in=mrm_mission_ids).select_related('mission')
    for h in legacy.order_by('-created_at'):
        rows.append([
            'Quick assessment', h.mission.name, h.hazard_description[:80], h.get_category_display(),
            h.initial_risk_level.replace('_', ' ').title(),
            h.residual_risk_level.replace('_', ' ').title() if h.residual_risk_level else '—',
        ])
    return title, headers, rows


def inventory_report():
    title = 'Inventory Report'
    headers = ['Item', 'Category', 'Type', 'On Hand', 'Reorder Level', 'Condition', 'Custodian']
    rows = [
        [
            i.name, i.category.name if i.category else '—', i.get_item_type_display(),
            f'{i.quantity_on_hand} {i.unit_of_measure}', i.reorder_level, i.get_condition_display(),
            i.accountable_personnel.full_name if i.accountable_personnel else '—',
        ]
        for i in InventoryItem.objects.filter(is_active=True).select_related('category', 'accountable_personnel').order_by('name')
    ]
    return title, headers, rows


REPORT_REGISTRY = {
    'PERSONNEL': personnel_report,
    'VEHICLE': vehicle_report,
    'FLIGHT': flight_report,
    'MISSION': mission_report,
    'RISK': risk_report,
    'INVENTORY': inventory_report,
}
