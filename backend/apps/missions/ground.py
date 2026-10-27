"""
Category-driven mission planning, submission and approval.

Design
------
* `CATEGORY_SPECS` is the extension point: each mission category (Ground / Air Operations) registers a spec that
  validates its payload and writes its own child records. Air Operations is registered but disabled until its
  flight-mission requirements exist — adding it later means filling in `AirOperationsSpec`, not reworking the module.
* Mission **approval** (by the selected authority) and MRM **preparation/approval** (apps.mrm) are separate
  workflows. Nothing here ever completes an MRM, and an MRM never approves a mission.
* Every write is one database transaction; notifications are queued with `transaction.on_commit`, so they are
  sent only for changes that really persisted and never twice for a repeated submit.
"""
import uuid

from django.contrib.gis.geos import Point
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.core.audit import log_action
from apps.core.models import AuditLog, Notification
from apps.core.notifications import notify
from apps.core.permissions import has_module_permission
from apps.core.rbac import Action, Module
from apps.gis.utils import MGRSError, latlon_to_mgrs, mgrs_to_latlon
from apps.personnel.models import Personnel, Section, Unit
from apps.vehicles.models import Vehicle

from .models import (
    Mission, MissionApprovalLog, MissionItinerary, MissionItineraryStop, MissionPersonnel, MissionVehicle,
)

# Designations (apps.accounts.User.MRMDesignation) whose holders may be chosen as a mission's approving authority.
MISSION_AUTHORITY_DESIGNATIONS = ('SQUADRON_COMMANDER', 'DIRECTOR_FOR_OPERATIONS', 'COMMANDER')
EDITABLE_APPROVAL_STATES = (Mission.ApprovalStatus.DRAFT, Mission.ApprovalStatus.REJECTED)
COORD_DISAGREEMENT_METERS = 250


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

class ErrorBag:
    """Collects field errors keyed by path (e.g. 'vehicles[0].itinerary[1].origin') so the UI can show each beside its field."""

    def __init__(self):
        self.errors = {}

    def add(self, path, message):
        self.errors.setdefault(path, []).append(message)

    def raise_if_any(self):
        if self.errors:
            raise ValidationError(self.errors)


def visible_unit_ids(user):
    """None = every unit (ADMIN/COMMANDER); otherwise the user's unit and everything beneath it."""
    if user.is_superuser or user.role in ('ADMIN', 'COMMANDER'):
        return None
    if not user.unit_id:
        return set()
    return set(user.unit.get_descendant_ids(include_self=True))


def _in_scope(user, unit_id):
    scope = visible_unit_ids(user)
    return scope is None or unit_id in scope


def _get(model, pk, **filters):
    if pk in (None, ''):
        return None
    try:
        return model.objects.filter(pk=pk, **filters).first()
    except Exception:  # malformed UUID
        return None


def _parse_datetime(value, bag, path, required=True, label='This field'):
    if value in (None, ''):
        if required:
            bag.add(path, f'{label} is required.')
        return None
    try:
        return serializers.DateTimeField().to_internal_value(value)
    except serializers.ValidationError:
        bag.add(path, f'{label} is not a valid date and time.')
        return None


def _haversine_m(lat1, lon1, lat2, lon2):
    import math

    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 12742000 * math.asin(math.sqrt(a))


def resolve_place(spec, bag, path, label):
    """
    A place is given as lat/lng and/or an MGRS string. Returns (Point, mgrs_string) or (None, '').
    lat/lng wins when both are present, but they must agree (the UI fills both from one source).
    """
    spec = spec or {}
    name = (spec.get('name') or '').strip()
    if not name:
        bag.add(f'{path}.name', f'{label} name is required.')
    lat, lng, mgrs_text = spec.get('lat'), spec.get('lng'), (spec.get('mgrs') or '').strip()

    parsed = None
    if lat not in (None, '') or lng not in (None, ''):
        try:
            lat_f, lng_f = float(lat), float(lng)
        except (TypeError, ValueError):
            bag.add(f'{path}.location', f'{label}: latitude and longitude must both be numbers.')
            return None, ''
        if not (-90 <= lat_f <= 90 and -180 <= lng_f <= 180):
            bag.add(f'{path}.location', f'{label}: latitude must be -90…90 and longitude -180…180.')
            return None, ''
        parsed = (lat_f, lng_f)
    if mgrs_text:
        try:
            mgrs_ll = mgrs_to_latlon(mgrs_text)
        except MGRSError as exc:
            bag.add(f'{path}.mgrs', f'{label}: {exc}')
            return None, ''
        if parsed and _haversine_m(*parsed, *mgrs_ll) > COORD_DISAGREEMENT_METERS:
            bag.add(f'{path}.mgrs', f'{label}: the MGRS reference and the map position are more than {COORD_DISAGREEMENT_METERS} m apart.')
            return None, ''
        parsed = parsed or mgrs_ll
    if parsed is None:
        bag.add(f'{path}.location', f'{label}: choose a point on the map or enter an MGRS reference.')
        return None, ''
    return Point(parsed[1], parsed[0], srid=4326), (latlon_to_mgrs(*parsed) or '')


# ---------------------------------------------------------------------------
# Candidates (who may be selected)
# ---------------------------------------------------------------------------

def _unit_chain(unit):
    chain, seen, current = [unit], {unit.pk}, unit.parent_unit
    while current is not None and current.pk not in seen:
        chain.append(current)
        seen.add(current.pk)
        current = current.parent_unit
    return chain


def mission_authority_candidates(unit, exclude_user=None):
    """
    Approving-authority choices for a mission owned by `unit`: active commanders/designated authorities in that unit or
    any mother unit, who actually hold the MISSIONS:APPROVE permission. The creator is never a candidate.
    """
    chain = _unit_chain(unit)
    qs = User.objects.filter(is_active=True, unit__in=chain).filter(
        Q(mrm_designation__in=MISSION_AUTHORITY_DESIGNATIONS) | Q(role=User.Role.COMMANDER)
    )
    if exclude_user is not None:
        qs = qs.exclude(pk=exclude_user.pk)
    rank = {u.pk: i for i, u in enumerate(chain)}
    people = [u for u in qs.select_related('unit') if has_module_permission(u, Module.MISSIONS, Action.APPROVE)]
    people.sort(key=lambda u: (rank.get(u.unit_id, 99), u.last_name, u.username))
    return people


def mrm_assignee_is_eligible(personnel):
    """A mission's MRM preparer needs an active linked account that is allowed to author MRM forms."""
    from apps.mrm.access import can_author

    account = personnel.linked_account
    return bool(account and account.is_active and can_author(account))


def mrm_assignee_candidates(mission):
    return [a.personnel for a in mission.personnel_assignments.select_related('personnel', 'personnel__linked_account', 'personnel__rank')
            if mrm_assignee_is_eligible(a.personnel)]


# ---------------------------------------------------------------------------
# Category specs
# ---------------------------------------------------------------------------

class CategorySpec:
    key = ''
    label = ''
    enabled = False
    description = ''

    def clean(self, user, data, instance):  # pragma: no cover - interface
        raise NotImplementedError

    def apply(self, mission, cleaned):  # pragma: no cover - interface
        raise NotImplementedError

    def completeness_errors(self, mission):
        return []


class GroundOperationsSpec(CategorySpec):
    key = Mission.Category.GROUND_OPERATIONS
    label = 'Ground Operations'
    enabled = True
    description = 'Ground missions and ground-based activities, with personnel, optional vehicle trips and itineraries.'

    # --- validation -------------------------------------------------------
    def clean(self, user, data, instance):
        bag = ErrorBag()
        out = {}

        name = (data.get('name') or '').strip()
        if not name:
            bag.add('name', 'Mission/Activity is required.')
        elif len(name) > 200:
            bag.add('name', 'Mission/Activity must be 200 characters or fewer.')
        out['name'] = name
        out['description'] = (data.get('description') or '').strip()

        start = _parse_datetime(data.get('start_date'), bag, 'start_date', label='Estimated start')
        end = _parse_datetime(data.get('end_date'), bag, 'end_date', label='Estimated end')
        if start and end and end < start:
            bag.add('end_date', 'Estimated end cannot be earlier than the estimated start.')
        out['start_date'], out['end_date'] = start, end

        unit = _get(Unit, data.get('unit'), is_active=True)
        if not data.get('unit'):
            bag.add('unit', 'Unit Primary Responsible (UPR) is required.')
        elif unit is None:
            bag.add('unit', 'The selected unit does not exist or is inactive.')
        elif not _in_scope(user, unit.pk):
            bag.add('unit', 'You can only plan missions for your own unit or the units beneath it.')
        out['unit'] = unit

        section = _get(Section, data.get('responsible_section'), is_active=True)
        if not data.get('responsible_section'):
            bag.add('responsible_section', 'Office/Section Primary Responsible (O/SPR) is required.')
        elif section is None:
            bag.add('responsible_section', 'The selected office/section does not exist or is inactive.')
        elif unit is not None and section.unit_id != unit.pk:
            bag.add('responsible_section', f'"{section.name}" does not belong to {unit.name}. Choose a section of the selected unit.')
        out['responsible_section'] = section

        people = self._clean_personnel(user, data.get('personnel'), bag)
        out['personnel'] = people
        person_ids = {p['personnel'].pk for p in people}

        out['vehicles'] = self._clean_vehicles(data.get('vehicles'), person_ids, bag)

        # Authority and MRM assignee may be chosen while drafting; they become mandatory at submission.
        out['approval_authority'] = None
        if data.get('approval_authority'):
            authority = _get(User, data.get('approval_authority'), is_active=True)
            allowed = {u.pk for u in mission_authority_candidates(unit, exclude_user=instance.created_by if instance else user)} if unit else set()
            if authority is None or authority.pk not in allowed:
                bag.add('approval_authority', 'The selected authority is not an eligible approver for this unit.')
            else:
                out['approval_authority'] = authority

        out['mrm_assignee'] = None
        if data.get('mrm_assignee'):
            assignee = _get(Personnel, data.get('mrm_assignee'), is_active=True)
            if assignee is None or assignee.pk not in person_ids:
                bag.add('mrm_assignee', 'The MRM assignee must be one of the personnel assigned to this mission.')
            elif not mrm_assignee_is_eligible(assignee):
                bag.add('mrm_assignee', f'{assignee.full_name} cannot prepare MRM forms (needs an active account with MRM Creator/Evaluator authority).')
            else:
                out['mrm_assignee'] = assignee

        bag.raise_if_any()
        return out

    @staticmethod
    def _clean_personnel(user, rows, bag):
        rows = rows or []
        if not isinstance(rows, list) or not rows:
            bag.add('personnel', 'Assign at least one person to the mission.')
            return []
        cleaned, seen, leaders = [], set(), 0
        scope = visible_unit_ids(user)
        valid_roles = {r.value for r in MissionPersonnel.Role}
        for i, row in enumerate(rows):
            path = f'personnel[{i}]'
            person = _get(Personnel, row.get('personnel'), is_active=True)
            if person is None:
                bag.add(f'{path}.personnel', 'Select a person from the Personnel Inventory.')
                continue
            if scope is not None and person.unit_id not in scope:
                bag.add(f'{path}.personnel', f'{person.full_name} belongs to a unit outside your scope.')
            if person.pk in seen:
                bag.add(f'{path}.personnel', f'{person.full_name} is already assigned to this mission.')
                continue
            seen.add(person.pk)
            role = row.get('role') or ''
            if role not in valid_roles:
                bag.add(f'{path}.role', 'Choose a role for this person.')
                continue
            role_other = (row.get('role_other') or '').strip()
            if role == MissionPersonnel.Role.OTHER and not role_other:
                bag.add(f'{path}.role_other', 'Describe the role.')
            if len(role_other) > 100:
                bag.add(f'{path}.role_other', 'Role description must be 100 characters or fewer.')
            if role == MissionPersonnel.Role.TEAM_LEADER:
                leaders += 1
            cleaned.append({'personnel': person, 'role': role, 'role_other': role_other if role == MissionPersonnel.Role.OTHER else ''})
        if leaders == 0:
            bag.add('personnel', 'Assign exactly one Team Leader.')
        elif leaders > 1:
            bag.add('personnel', 'Only one person can be the Team Leader.')
        return cleaned

    def _clean_vehicles(self, rows, person_ids, bag):
        rows = rows or []
        if not isinstance(rows, list):
            bag.add('vehicles', 'Vehicles must be a list.')
            return []
        cleaned, fleet_seen, pov_seen = [], set(), set()
        for i, row in enumerate(rows):
            path = f'vehicles[{i}]'
            is_pov = bool(row.get('is_pov'))
            entry = {'is_pov': is_pov, 'vehicle': None, 'pov': {}, 'driver': None, 'notes': (row.get('notes') or '').strip(), 'itinerary': []}

            if is_pov:
                pov = row.get('pov') or {}
                plate = (pov.get('plate_number') or '').strip().upper()
                vtype = (pov.get('vehicle_type') or '').strip()
                if not plate:
                    bag.add(f'{path}.pov.plate_number', 'Plate number is required for a privately owned vehicle.')
                elif len(plate) > 20:
                    bag.add(f'{path}.pov.plate_number', 'Plate number must be 20 characters or fewer.')
                elif Vehicle.objects.filter(plate_number__iexact=plate).exists():
                    bag.add(f'{path}.pov.plate_number', f'{plate} is an official fleet vehicle — select it from the Vehicle Inventory instead of adding it as a POV.')
                elif plate in pov_seen:
                    bag.add(f'{path}.pov.plate_number', f'POV {plate} is already on this mission.')
                pov_seen.add(plate)
                if not vtype:
                    bag.add(f'{path}.pov.vehicle_type', 'Vehicle type is required.')
                for field, limit in (('vehicle_type', 100), ('make', 100), ('model', 100), ('color', 50), ('owner_name', 150)):
                    if len((pov.get(field) or '')) > limit:
                        bag.add(f'{path}.pov.{field}', f'Must be {limit} characters or fewer.')
                entry['pov'] = {
                    'plate_number': plate, 'vehicle_type': vtype, 'make': (pov.get('make') or '').strip(),
                    'model': (pov.get('model') or '').strip(), 'color': (pov.get('color') or '').strip(),
                    'owner_name': (pov.get('owner_name') or '').strip(), 'description': (pov.get('description') or '').strip(),
                }
            else:
                vehicle = _get(Vehicle, row.get('vehicle'), is_active=True)
                if vehicle is None:
                    bag.add(f'{path}.vehicle', 'Select a vehicle from the Vehicle Inventory (or add a POV).')
                elif vehicle.pk in fleet_seen:
                    bag.add(f'{path}.vehicle', f'{vehicle.plate_number} is already on this mission.')
                else:
                    fleet_seen.add(vehicle.pk)
                    entry['vehicle'] = vehicle

            if row.get('driver'):
                driver = _get(Personnel, row.get('driver'), is_active=True)
                if driver is None or driver.pk not in person_ids:
                    bag.add(f'{path}.driver', 'The driver must be one of the personnel assigned to this mission.')
                else:
                    entry['driver'] = driver

            entry['itinerary'] = self._clean_itinerary(row.get('itinerary'), path, bag)
            cleaned.append(entry)
        return cleaned

    @staticmethod
    def _clean_itinerary(legs, path, bag):
        legs = legs or []
        if not isinstance(legs, list):
            bag.add(f'{path}.itinerary', 'Itinerary must be a list.')
            return []
        cleaned = []
        for j, leg in enumerate(legs):
            lp = f'{path}.itinerary[{j}]'
            o_point, o_mgrs = resolve_place(leg.get('origin'), bag, f'{lp}.origin', 'Origin')
            d_point, d_mgrs = resolve_place(leg.get('destination'), bag, f'{lp}.destination', 'Destination')
            dep = _parse_datetime(leg.get('planned_departure'), bag, f'{lp}.planned_departure', required=False, label='Departure')
            arr = _parse_datetime(leg.get('planned_arrival'), bag, f'{lp}.planned_arrival', required=False, label='Arrival')
            if dep and arr and arr < dep:
                bag.add(f'{lp}.planned_arrival', 'Arrival cannot be earlier than departure.')
            stops = []
            for k, stop in enumerate(leg.get('stops') or []):
                point, mgrs_text = resolve_place(stop, bag, f'{lp}.stops[{k}]', f'Stop {k + 1}')
                stops.append({'name': (stop.get('name') or '').strip()[:200], 'point': point, 'mgrs': mgrs_text, 'notes': (stop.get('notes') or '').strip()})
            cleaned.append({
                'origin': {'name': ((leg.get('origin') or {}).get('name') or '').strip()[:200], 'point': o_point, 'mgrs': o_mgrs},
                'destination': {'name': ((leg.get('destination') or {}).get('name') or '').strip()[:200], 'point': d_point, 'mgrs': d_mgrs},
                'planned_departure': dep, 'planned_arrival': arr, 'notes': (leg.get('notes') or '').strip(), 'stops': stops,
            })
        return cleaned

    # --- persistence ------------------------------------------------------
    def apply(self, mission, cleaned):
        mission.name = cleaned['name']
        mission.description = cleaned['description']
        mission.start_date, mission.end_date = cleaned['start_date'], cleaned['end_date']
        mission.unit, mission.responsible_section = cleaned['unit'], cleaned['responsible_section']
        mission.approval_authority, mission.mrm_assignee = cleaned['approval_authority'], cleaned['mrm_assignee']
        mission.save()

        # Replace the planning records wholesale inside the same transaction (no partial states, no duplicates).
        mission.personnel_assignments.all().delete()
        mission.vehicle_assignments.all().delete()
        MissionPersonnel.objects.bulk_create([
            MissionPersonnel(mission=mission, personnel=p['personnel'], role=p['role'], role_other=p['role_other'])
            for p in cleaned['personnel']
        ])
        for seq, v in enumerate(cleaned['vehicles'], start=1):
            pov = v['pov']
            mv = MissionVehicle.objects.create(
                mission=mission, sequence=seq, is_pov=v['is_pov'], vehicle=v['vehicle'], driver=v['driver'], notes=v['notes'],
                pov_plate_number=pov.get('plate_number', ''), pov_vehicle_type=pov.get('vehicle_type', ''),
                pov_make=pov.get('make', ''), pov_model=pov.get('model', ''), pov_color=pov.get('color', ''),
                pov_owner_name=pov.get('owner_name', ''), pov_description=pov.get('description', ''),
            )
            for lseq, leg in enumerate(v['itinerary'], start=1):
                it = MissionItinerary.objects.create(
                    vehicle_assignment=mv, sequence=lseq,
                    origin_name=leg['origin']['name'], origin_location=leg['origin']['point'], origin_mgrs=leg['origin']['mgrs'],
                    destination_name=leg['destination']['name'], destination_location=leg['destination']['point'],
                    destination_mgrs=leg['destination']['mgrs'],
                    planned_departure=leg['planned_departure'], planned_arrival=leg['planned_arrival'], notes=leg['notes'],
                )
                MissionItineraryStop.objects.bulk_create([
                    MissionItineraryStop(itinerary=it, sequence=sseq, name=s['name'] or f'Stop {sseq}', location=s['point'], mgrs=s['mgrs'], notes=s['notes'])
                    for sseq, s in enumerate(leg['stops'], start=1)
                ])

    def completeness_errors(self, mission):
        problems = []
        if not mission.personnel_assignments.filter(role=MissionPersonnel.Role.TEAM_LEADER).exists():
            problems.append('Assign a Team Leader.')
        if mission.responsible_section_id is None:
            problems.append('Select the Office/Section Primary Responsible.')
        return problems


class AirOperationsSpec(CategorySpec):
    """Placeholder: the flight-mission field structure is still to be specified."""

    key = Mission.Category.AIR_OPERATIONS
    label = 'Air Operations'
    enabled = False
    description = 'Flight missions. The detailed form is pending its requirements.'

    def clean(self, user, data, instance):
        raise ValidationError({'category': 'Air Operations missions cannot be created yet — the flight mission form is awaiting its requirements.'})

    def apply(self, mission, cleaned):  # pragma: no cover
        raise NotImplementedError


CATEGORY_SPECS = {s.key: s for s in (GroundOperationsSpec(), AirOperationsSpec())}


def category_catalog():
    return [{'key': s.key, 'label': s.label, 'enabled': s.enabled, 'description': s.description} for s in CATEGORY_SPECS.values()]


# ---------------------------------------------------------------------------
# Save (create / update)
# ---------------------------------------------------------------------------

def can_edit_mission(user, mission):
    if mission.approval_status not in EDITABLE_APPROVAL_STATES:
        return False
    if user.is_superuser or user.role in ('ADMIN', 'COMMANDER') or mission.created_by_id == user.id:
        return True
    return has_module_permission(user, Module.MISSIONS, Action.EDIT) and (
        mission.unit_id is None or _in_scope(user, mission.unit_id)
    )


def _parse_token(value):
    if value in (None, ''):
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError:
        raise ValidationError({'client_request_id': 'Must be a UUID.'})


def save_mission(user, data, instance=None, request=None):
    """Create or update a categorised mission. Returns (mission, created)."""
    token = _parse_token(data.get('client_request_id')) if instance is None else None
    if token:
        existing = Mission.objects.filter(client_request_id=token).first()
        if existing is not None:
            if existing.created_by_id != user.id:
                raise PermissionDenied('That request token belongs to another user.')
            return existing, False   # idempotent replay — a double click never creates a second mission

    category = (instance.category if instance is not None else '') or data.get('category') or ''
    if instance is not None and instance.category and data.get('category') not in (None, '', instance.category):
        raise ValidationError({'category': 'A mission\'s category cannot be changed after it is created.'})
    spec = CATEGORY_SPECS.get(category)
    if spec is None:
        raise ValidationError({'category': 'Select a mission category (Air Operations or Ground Operations).'})
    if instance is not None and not can_edit_mission(user, instance):
        raise PermissionDenied('This mission can no longer be edited (it is awaiting or has received approval) or you may not edit it.')

    try:
        with transaction.atomic():
            cleaned = spec.clean(user, data, instance)
            mission = instance or Mission(created_by=user, category=category, client_request_id=token)
            before_authority = getattr(instance, 'approval_authority_id', None)
            spec.apply(mission, cleaned)
            log_action(
                user=user, action=AuditLog.Action.UPDATE if instance else AuditLog.Action.CREATE, instance=mission,
                description=f'{"Updated" if instance else "Created"} {spec.label} mission "{mission.name}"',
                metadata={'category': category, 'personnel': len(cleaned['personnel']), 'vehicles': len(cleaned['vehicles']),
                          'authority_changed': before_authority != mission.approval_authority_id},
                request=request,
            )
    except IntegrityError:
        # Lost a race on the idempotency token: hand back the mission the other request created.
        existing = Mission.objects.filter(client_request_id=token).first() if token else None
        if existing is not None:
            return existing, False
        raise ValidationError({'detail': 'The mission could not be saved because it conflicts with existing data. Please review it and try again.'})
    return mission, instance is None


# ---------------------------------------------------------------------------
# Submission and approval
# ---------------------------------------------------------------------------

def _lock(mission):
    return Mission.objects.select_for_update().get(pk=mission.pk)


def submit_mission(user, mission, request=None):
    """
    Draft/rejected -> pending approval. Idempotent: submitting an already-pending mission changes nothing and
    notifies nobody again. Returns (mission, newly_submitted).
    """
    with transaction.atomic():
        mission = _lock(mission)
        if mission.approval_status == Mission.ApprovalStatus.PENDING:
            return mission, False
        if mission.approval_status == Mission.ApprovalStatus.APPROVED:
            raise ValidationError({'detail': 'This mission is already approved.'})
        if not (mission.created_by_id == user.id or user.is_superuser or user.role == 'ADMIN'):
            raise PermissionDenied('Only the mission creator can submit it for approval.')
        spec = CATEGORY_SPECS.get(mission.category)
        if spec is None or not spec.enabled:
            raise ValidationError({'category': 'This mission has no submittable category.'})

        problems = list(spec.completeness_errors(mission))
        errors = {}
        if mission.approval_authority_id is None:
            errors['approval_authority'] = ['Select the approving authority before submitting.']
        elif mission.approval_authority_id == mission.created_by_id:
            errors['approval_authority'] = ['You cannot be the approving authority of your own mission.']
        elif not mission.approval_authority.is_active:
            errors['approval_authority'] = ['The selected authority is no longer active — choose another.']
        if mission.mrm_assignee_id is None:
            errors['mrm_assignee'] = ['Select who will prepare the Mission Risk Management (MRM) form.']
        elif not mission.personnel_assignments.filter(personnel_id=mission.mrm_assignee_id).exists():
            errors['mrm_assignee'] = ['The MRM assignee is no longer assigned to this mission.']
        elif not mrm_assignee_is_eligible(mission.mrm_assignee):
            errors['mrm_assignee'] = ['The MRM assignee can no longer prepare MRM forms.']
        if problems:
            errors['detail'] = problems
        if errors:
            raise ValidationError(errors)

        now = timezone.now()
        mission.approval_status = Mission.ApprovalStatus.PENDING
        mission.approval_submitted_at = now
        mission.approval_decided_by, mission.approval_decided_at, mission.approval_comments = None, None, ''
        mission.save(update_fields=['approval_status', 'approval_submitted_at', 'approval_decided_by',
                                    'approval_decided_at', 'approval_comments', 'updated_at'])
        submission = MissionApprovalLog.objects.create(mission=mission, workflow=MissionApprovalLog.Workflow.MISSION_APPROVAL,
                                                       action=MissionApprovalLog.Action.SUBMITTED, actor=user)
        log_action(user=user, action=AuditLog.Action.OTHER, instance=mission,
                   description=f'Submitted mission "{mission.name}" to {mission.approval_authority.username} for approval', request=request)

        link = f'/missions/{mission.pk}'
        meta = {'mission_id': str(mission.pk)}
        notify([mission.approval_authority], Notification.Kind.MISSION_APPROVAL_REQUEST,
               f'Mission awaiting your approval: {mission.name}',
               f'{user.full_name} submitted this mission. Review it and approve or reject.', link,
               dedupe_key=f'mission-approval:{submission.pk}', metadata=meta)
        assignee_account = mission.mrm_assignee.linked_account
        notify([assignee_account], Notification.Kind.MRM_PREPARATION_REQUEST,
               f'Prepare the MRM for: {mission.name}',
               'You were designated to prepare the Mission Risk Management form for this mission.',
               f'/mrm/new?mission={mission.pk}',
               dedupe_key=f'mission-mrm:{mission.pk}:{mission.mrm_assignee_id}', metadata=meta)
    return mission, True


def can_decide(user, mission):
    """The selected authority (never the creator) — who must also hold the MISSIONS:APPROVE permission."""
    if mission.approval_status != Mission.ApprovalStatus.PENDING or user.pk == mission.created_by_id:
        return False
    if not has_module_permission(user, Module.MISSIONS, Action.APPROVE):
        return False
    return mission.approval_authority_id == user.pk or user.is_superuser or user.role == User.Role.ADMIN


def decide_mission(user, mission, approve, comments='', request=None):
    comments = (comments or '').strip()
    with transaction.atomic():
        mission = _lock(mission)
        if mission.approval_status != Mission.ApprovalStatus.PENDING:
            raise ValidationError({'detail': f'This mission is not awaiting approval (it is {mission.get_approval_status_display().lower()}).'})
        if user.pk == mission.created_by_id:
            raise PermissionDenied('You cannot approve or reject your own mission.')
        if not can_decide(user, mission):
            raise PermissionDenied('Only the selected approving authority can decide on this mission.')
        if not approve and not comments:
            raise ValidationError({'comments': 'Give a reason for rejecting the mission.'})

        mission.approval_status = Mission.ApprovalStatus.APPROVED if approve else Mission.ApprovalStatus.REJECTED
        mission.approval_decided_by, mission.approval_decided_at, mission.approval_comments = user, timezone.now(), comments
        update = ['approval_status', 'approval_decided_by', 'approval_decided_at', 'approval_comments', 'updated_at']
        if approve and mission.status == Mission.Status.PLANNED:
            mission.status = Mission.Status.APPROVED
            update.append('status')
        mission.save(update_fields=update)
        decision = MissionApprovalLog.objects.create(
            mission=mission, workflow=MissionApprovalLog.Workflow.MISSION_APPROVAL, actor=user, comments=comments,
            action=MissionApprovalLog.Action.APPROVED if approve else MissionApprovalLog.Action.REJECTED,
        )
        log_action(user=user, action=AuditLog.Action.APPROVE if approve else AuditLog.Action.REJECT, instance=mission,
                   description=f'{"Approved" if approve else "Rejected"} mission "{mission.name}"', request=request)

        verdict = 'approved' if approve else 'rejected'
        notify([mission.created_by],
               Notification.Kind.MISSION_APPROVED if approve else Notification.Kind.MISSION_REJECTED,
               f'Your mission was {verdict}: {mission.name}',
               comments or f'{user.full_name} {verdict} the mission.', f'/missions/{mission.pk}',
               dedupe_key=f'mission-decision:{decision.pk}',
               metadata={'mission_id': str(mission.pk)})
    return mission


# ---------------------------------------------------------------------------
# Derived MRM tracking (separate from approval)
# ---------------------------------------------------------------------------

MRM_STAGE_TO_PREP = {
    'draft': 'IN_PROGRESS', 'needs_revision': 'REVISION_REQUIRED', 'rejected': 'REVISION_REQUIRED',
    'awaiting_review': 'SUBMITTED', 'awaiting_authority': 'SUBMITTED', 'needs_authority_assignment': 'SUBMITTED',
    'approved': 'APPROVED',
}
MRM_PREP_LABELS = {
    'NOT_STARTED': 'Not started', 'IN_PROGRESS': 'In progress', 'REVISION_REQUIRED': 'Revision required',
    'SUBMITTED': 'Submitted', 'APPROVED': 'Approved',
}


def mrm_preparation_status(mission):
    """Derived from the mission's real MRM form — never stored, so it cannot drift or be marked complete by hand."""
    form = mission.active_mrm
    if form is None:
        return 'NOT_STARTED'
    from apps.mrm.serializers import stage_of

    return MRM_STAGE_TO_PREP[stage_of(form)]


# ---------------------------------------------------------------------------
# Serialisation of the planning sections
# ---------------------------------------------------------------------------

def _point(p):
    return {'lat': p.y, 'lng': p.x} if p is not None else None


def _person_brief(p):
    if p is None:
        return None
    return {'id': str(p.pk), 'name': p.full_name, 'service_number': p.service_number,
            'rank': p.rank.abbreviation if p.rank_id else '', 'unit': p.unit.code if p.unit_id else None,
            'has_account': bool(p.linked_account_id)}


def serialize_planning(mission, user):
    people = list(mission.personnel_assignments.select_related('personnel', 'personnel__rank', 'personnel__unit'))
    vehicles = list(
        mission.vehicle_assignments.select_related('vehicle', 'driver', 'driver__rank')
        .prefetch_related('itinerary', 'itinerary__stops')
    )
    authority = mission.approval_authority
    assignee = mission.mrm_assignee
    form = mission.active_mrm
    prep = mrm_preparation_status(mission)
    account = getattr(assignee, 'linked_account', None) if assignee else None
    return {
        'category': mission.category,
        'category_label': mission.get_category_display() if mission.category else 'Uncategorized (legacy)',
        'unit_name': mission.unit.name if mission.unit_id else None,
        'unit_code': mission.unit.code if mission.unit_id else None,
        'responsible_section_name': mission.responsible_section.name if mission.responsible_section_id else None,
        'created_by': str(mission.created_by_id) if mission.created_by_id else None,
        'created_by_name': mission.created_by.full_name if mission.created_by_id else None,
        'personnel': [{
            'id': str(a.pk), 'personnel': str(a.personnel_id), 'role': a.role, 'role_other': a.role_other, 'role_label': a.role_label,
            'person': _person_brief(a.personnel),
        } for a in people],
        'vehicles': [{
            'id': str(v.pk), 'is_pov': v.is_pov, 'sequence': v.sequence, 'vehicle': str(v.vehicle_id) if v.vehicle_id else None,
            'fleet': ({'plate_number': v.vehicle.plate_number, 'vehicle_type': v.vehicle.vehicle_type, 'make': v.vehicle.make,
                       'model': v.vehicle.model} if v.vehicle_id else None),
            'pov': ({'plate_number': v.pov_plate_number, 'vehicle_type': v.pov_vehicle_type, 'make': v.pov_make, 'model': v.pov_model,
                     'color': v.pov_color, 'owner_name': v.pov_owner_name, 'description': v.pov_description} if v.is_pov else None),
            'driver': str(v.driver_id) if v.driver_id else None, 'driver_name': v.driver.full_name if v.driver_id else None,
            'notes': v.notes,
            'itinerary': [{
                'id': str(it.pk), 'sequence': it.sequence,
                'origin': {'name': it.origin_name, **_point(it.origin_location), 'mgrs': it.origin_mgrs},
                'destination': {'name': it.destination_name, **_point(it.destination_location), 'mgrs': it.destination_mgrs},
                'planned_departure': it.planned_departure, 'planned_arrival': it.planned_arrival, 'notes': it.notes,
                'stops': [{'sequence': s.sequence, 'name': s.name, **_point(s.location), 'mgrs': s.mgrs, 'notes': s.notes} for s in it.stops.all()],
            } for it in v.itinerary.all()],
        } for v in vehicles],
        'approval': {
            'status': mission.approval_status, 'status_label': mission.get_approval_status_display(),
            'authority': ({'id': str(authority.pk), 'name': authority.display_name_with_rank, 'designation': authority.mrm_designation,
                           'unit': authority.unit.code if authority.unit_id else None} if authority else None),
            'submitted_at': mission.approval_submitted_at,
            'decided_by_name': mission.approval_decided_by.full_name if mission.approval_decided_by_id else None,
            'decided_at': mission.approval_decided_at, 'comments': mission.approval_comments,
        },
        'mrm_assignee': ({**_person_brief(assignee), 'account_id': str(account.pk) if account else None} if assignee else None),
        'mrm_preparation': {
            'status': prep, 'label': MRM_PREP_LABELS[prep], 'form_id': str(form.pk) if form else None,
            'mrm_number': form.mrm_number if form else None,
        },
        'can': {
            'edit': can_edit_mission(user, mission) and mission.category != '',
            'submit': mission.category != '' and mission.approval_status in EDITABLE_APPROVAL_STATES
                      and (mission.created_by_id == user.id or user.is_superuser or user.role == 'ADMIN'),
            'decide': can_decide(user, mission),
            'prepare_mrm': bool(assignee and account and account.pk == user.pk and form is None),
        },
    }


def mission_activity(mission):
    """Chronological history: approval decisions, audited changes and notifications sent for this mission."""
    events = []
    for log in mission.approval_logs.select_related('actor'):
        events.append({
            'when': log.created_at, 'kind': 'approval' if log.workflow == MissionApprovalLog.Workflow.MISSION_APPROVAL else 'risk_review',
            'title': f'{log.get_workflow_display()}: {log.get_action_display()}',
            'actor': log.actor.full_name if log.actor_id else 'System', 'detail': log.comments,
        })
    for entry in AuditLog.objects.filter(model_name='Mission', object_id=str(mission.pk)).select_related('user'):
        events.append({'when': entry.created_at, 'kind': 'audit', 'title': entry.description or entry.get_action_display(),
                       'actor': entry.user.full_name if entry.user_id else 'System', 'detail': ''})
    for n in Notification.objects.filter(metadata__mission_id=str(mission.pk)).select_related('user'):
        events.append({'when': n.created_at, 'kind': 'notification', 'title': f'Notified {n.user.full_name}: {n.title}',
                       'actor': 'System', 'detail': 'read' if n.is_read else 'unread'})
    events.sort(key=lambda e: e['when'], reverse=True)
    return events


def payload_from_instance(mission):
    """The save_mission() payload that reproduces `mission` — lets PATCH send only the fields that changed."""
    def place(name, point, mgrs):
        return {'name': name, 'lat': point.y, 'lng': point.x, 'mgrs': mgrs}

    vehicles = []
    for v in mission.vehicle_assignments.prefetch_related('itinerary', 'itinerary__stops'):
        vehicles.append({
            'is_pov': v.is_pov, 'vehicle': str(v.vehicle_id) if v.vehicle_id else None,
            'pov': {'plate_number': v.pov_plate_number, 'vehicle_type': v.pov_vehicle_type, 'make': v.pov_make, 'model': v.pov_model,
                    'color': v.pov_color, 'owner_name': v.pov_owner_name, 'description': v.pov_description} if v.is_pov else None,
            'driver': str(v.driver_id) if v.driver_id else None, 'notes': v.notes,
            'itinerary': [{
                'origin': place(it.origin_name, it.origin_location, it.origin_mgrs),
                'destination': place(it.destination_name, it.destination_location, it.destination_mgrs),
                'planned_departure': it.planned_departure.isoformat() if it.planned_departure else None,
                'planned_arrival': it.planned_arrival.isoformat() if it.planned_arrival else None, 'notes': it.notes,
                'stops': [{**place(st.name, st.location, st.mgrs), 'notes': st.notes} for st in it.stops.all()],
            } for it in v.itinerary.all()],
        })
    return {
        'category': mission.category, 'name': mission.name, 'description': mission.description,
        'start_date': mission.start_date.isoformat() if mission.start_date else None,
        'end_date': mission.end_date.isoformat() if mission.end_date else None,
        'unit': str(mission.unit_id) if mission.unit_id else None,
        'responsible_section': str(mission.responsible_section_id) if mission.responsible_section_id else None,
        'personnel': [{'personnel': str(a.personnel_id), 'role': a.role, 'role_other': a.role_other} for a in mission.personnel_assignments.all()],
        'vehicles': vehicles,
        'approval_authority': str(mission.approval_authority_id) if mission.approval_authority_id else None,
        'mrm_assignee': str(mission.mrm_assignee_id) if mission.mrm_assignee_id else None,
    }


PLANNING_KEYS = frozenset({
    'category', 'name', 'description', 'start_date', 'end_date', 'unit', 'responsible_section', 'personnel', 'vehicles',
    'approval_authority', 'mrm_assignee',
})
