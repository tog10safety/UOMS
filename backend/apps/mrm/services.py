"""
MRM workflow — the business rules the legacy Flask routes implemented inline.

Everything that mutates an MRM goes through here so that the REST API, the admin site and
the import command share one set of rules. Each function checks authority itself
(``apps.mrm.access``) and raises DRF ``PermissionDenied`` / ``ValidationError``.

State machine
-------------
  draft ──submit──▶ submitted ──review──▶ reviewed(approved) ──authority approve──▶ APPROVED (locked)
     ▲                  │                       │
     │                  └─ review: rejected / needs_revision ─▶ reviewed(rejected|needs_revision)
     └──────────── creator revises & re-submits ◀─────────────────┘

(The legacy app dead-ended rejected forms; here the creator can revise and re-submit.)
"""
import logging
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.core.audit import log_action
from apps.core.models import AuditLog

from . import access, risk
from .constants import ENVIRONMENT_FIELDS, IMSAFE_CHECKLIST, DEFAULT_MISSION_STATEMENT
from .constants import LIGHTING_OPTIONS, OPERATIONAL_TEMPO_OPTIONS, WEATHER_OPTIONS, WORKSPACE_OPTIONS
from .models import (
    FeedbackNotification, Hazard, MissionHazard, MRMEvent, MRMFeedback, MRMForm, MRMPersonnel,
)

logger = logging.getLogger(__name__)
PH_TZ = ZoneInfo('Asia/Manila')
A = User.MRMAuthority

ENV_OPTIONS = {
    'weather': WEATHER_OPTIONS,
    'lighting': LIGHTING_OPTIONS,
    'workspace': WORKSPACE_OPTIONS,
    'operational_tempo': OPERATIONAL_TEMPO_OPTIONS,
}


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _event(form, kind, user=None, comments='', **metadata):
    return MRMEvent.objects.create(
        mrm=form, kind=kind, actor=user, actor_name=user.display_name_with_rank if user else '',
        comments=comments, metadata=metadata,
    )


def _audit(user, action, form, description, request=None):
    log_action(user=user, action=action, instance=form, description=description, request=request)


def generate_mrm_number():
    """YYYYMMDD + running number for the day (Philippine time), e.g. 2026101001."""
    today = timezone.now().astimezone(PH_TZ).strftime('%Y%m%d')
    suffixes = MRMForm.objects.filter(mrm_number__startswith=today).values_list('mrm_number', flat=True)
    highest = 0
    for number in suffixes:
        tail = number[len(today):]
        if tail.isdigit():
            highest = max(highest, int(tail))
    return f'{today}{highest + 1:02d}'


def render_environment(data):
    parts = [str(data[k]).capitalize() for k in ENVIRONMENT_FIELDS if data.get(k)]
    return '. '.join(parts) + '.' if parts else 'Standard operational environment.'


def clean_environment(data, required=True):
    data = data or {}
    env = {k: (data.get(k) or '').strip() for k in ENVIRONMENT_FIELDS}
    if required and not all(env.values()):
        raise ValidationError({'environment': 'All environment fields (weather, lighting, workspace, operational tempo) are required.'})
    for key, value in env.items():
        if value and value not in ENV_OPTIONS[key]:
            raise ValidationError({'environment': f'"{value}" is not a valid {key.replace("_", " ")} option.'})
    return env


def clean_imsafe(data, required=True):
    data = data or {}
    cleaned = {key: bool(data.get(key)) for key in IMSAFE_CHECKLIST}
    if required and not all(cleaned.values()):
        raise ValidationError({'imsafe': "All I'M SAFE checklist items must be confirmed."})
    return cleaned


def _full_name(user):
    return user.display_name_with_rank if user else ''


# ---------------------------------------------------------------------------
# hazards & risk
# ---------------------------------------------------------------------------

def _clean_hazard_items(user, form_unit, items, existing_hazard_ids=()):
    if not items:
        raise ValidationError({'hazards': 'At least one hazard must be selected.'})
    if len(items) > 100:
        raise ValidationError({'hazards': 'A single MRM may not contain more than 100 hazards.'})

    allowed = {h.id: h for h in access.pickable_hazards(user, form_unit)}
    allowed.update({h.id: h for h in Hazard.objects.filter(id__in=existing_hazard_ids)})  # keep what is already attached

    cleaned, seen = [], set()
    for index, item in enumerate(items):
        hazard_id = item.get('hazard') or item.get('id')
        hazard = allowed.get(hazard_id) or next((h for h in allowed.values() if str(h.id) == str(hazard_id)), None)
        if hazard is None:
            raise ValidationError({'hazards': f'Hazard #{index + 1} is not available to this unit.'})
        if hazard.id in seen:
            continue
        seen.add(hazard.id)

        likelihood = item.get('override_likelihood')
        severity = (item.get('override_severity') or '').strip().upper()
        notes = (item.get('additional_mitigations') or '').strip()
        if (likelihood in (None, '')) != (not severity):
            raise ValidationError({'hazards': 'An override needs both a likelihood and a severity.'})
        override = (None, '')
        if severity:
            try:
                likelihood, severity = risk.normalize(likelihood, severity)
            except risk.RiskInputError as exc:
                raise ValidationError({'hazards': str(exc)})
            if risk.rating(likelihood, severity) != hazard.after_risk_rating:
                if not notes:
                    raise ValidationError({'hazards': (
                        f'Changing the residual risk of "{hazard.hazard_description[:40]}…" away from the registry value '
                        f'({hazard.after_risk_rating}) requires a justification in additional mitigations.'
                    )})
                override = (likelihood, severity)
        cleaned.append({'hazard': hazard, 'override': override, 'notes': notes})
    return cleaned


def _apply_hazards(form, cleaned):
    keep = {c['hazard'].id for c in cleaned}
    form.mission_hazards.exclude(hazard_id__in=keep).delete()
    existing = {mh.hazard_id: mh for mh in form.mission_hazards.all()}
    for position, c in enumerate(cleaned):
        mh = existing.get(c['hazard'].id) or MissionHazard(mrm=form, hazard=c['hazard'])
        mh.override_likelihood, mh.override_severity = c['override'] if c['override'][0] else (None, '')
        mh.additional_mitigations = c['notes']
        mh.position = position
        mh.take_snapshot()
        mh.save()


def recalculate(form):
    hazards = list(form.mission_hazards.select_related('hazard'))
    summary = risk.summarize(mh.effective_residual for mh in hazards)
    form.max_risk = summary.max_risk
    form.residual_risk = summary.residual_risk
    form.total_percent = summary.total_percent
    form.authority_level = summary.authority_level
    form.risk_category = summary.risk_category
    form.save(update_fields=['max_risk', 'residual_risk', 'total_percent', 'authority_level', 'risk_category', 'updated_at'])
    return summary


def preview_risk(user, form_unit, items):
    """Live risk preview for the editor (no persistence)."""
    cleaned = _clean_hazard_items(user, form_unit, items)
    pairs = [c['override'] if c['override'][0] else (c['hazard'].after_likelihood, c['hazard'].after_severity) for c in cleaned]
    summary = risk.summarize(pairs)
    return {
        'max_risk': summary.max_risk, 'residual_risk': summary.residual_risk,
        'total_percent': summary.total_percent, 'authority_level': summary.authority_level,
        'authority_label': risk.AUTHORITY_LABELS[summary.authority_level], 'risk_category': summary.risk_category,
    }


# ---------------------------------------------------------------------------
# people
# ---------------------------------------------------------------------------

def _clean_reviewer(acting_user, creator, unit, reviewer_id):
    if not reviewer_id:
        raise ValidationError({'reviewer': 'Please select an evaluator to review this MRM.'})
    reviewer = User.objects.filter(pk=reviewer_id, is_active=True).first()
    if reviewer is None or reviewer.effective_mrm_authority != A.EVALUATOR:
        raise ValidationError({'reviewer': 'The selected reviewer is not an active Evaluator.'})
    if creator and reviewer.pk == creator.pk:
        raise ValidationError({'reviewer': 'You cannot review your own MRM — choose another evaluator.'})
    if not access.is_admin(acting_user):
        allowed = {u.pk for u in access.evaluator_candidates(unit, exclude_user=creator)}
        if reviewer.pk not in allowed:
            raise ValidationError({'reviewer': 'The selected evaluator is not in your unit (or a mother unit).'})
    return reviewer


def _sync_tagged(form, tagged, acting_user):
    wanted = {}
    for entry in tagged or []:
        user_id = entry.get('user') or entry.get('id')
        wanted[str(user_id)] = (entry.get('role') or 'Crew Member').strip()[:100]
    people = {str(u.pk): u for u in User.objects.filter(pk__in=list(wanted), is_active=True)}
    for key in wanted:
        person = people.get(key)
        if person is None or person.unit_id != form.unit_id:
            raise ValidationError({'tagged_personnel': 'Tagged personnel must be active users in the same unit as the MRM.'})
    for key, role in wanted.items():
        tag, _ = MRMPersonnel.objects.get_or_create(mrm=form, user=people[key], defaults={'role': role, 'tagged_by': acting_user})
        changed = False
        if not tag.is_active:
            tag.is_active, changed = True, True
        if tag.role != role:
            tag.role, changed = role, True
        if changed:
            tag.save()
    form.tagged_personnel.exclude(user_id__in=[p.pk for p in people.values()]).update(is_active=False)


def _resolve_mission(user, mission_id, form=None):
    if not mission_id:
        return None
    from apps.missions.models import Mission

    mission = Mission.objects.filter(pk=mission_id, is_active=True).first()
    if mission is None:
        raise ValidationError({'mission': 'Mission not found.'})
    is_assignee = bool(mission.mrm_assignee_id and mission.mrm_assignee.linked_account_id == user.pk)
    if mission.unit_id and not (is_assignee or access.is_admin(user) or user.role == User.Role.COMMANDER
                                or access.unit_in_scope(user, mission.unit_id)):
        raise ValidationError({'mission': 'That mission belongs to a unit outside your scope.'})
    clash = mission.mrm_forms.filter(is_active=True)
    if form is not None:
        clash = clash.exclude(pk=form.pk)
    if clash.exists():
        raise ValidationError({'mission': f'Mission "{mission.name}" already has an active MRM ({clash.first().mrm_number}).'})
    return mission


# ---------------------------------------------------------------------------
# create / update
# ---------------------------------------------------------------------------

@transaction.atomic
def create_mrm(user, data, request=None):
    if not access.can_author(user):
        raise PermissionDenied('Creator access required.')

    unit = user.unit
    if access.is_admin(user) and data.get('unit'):
        from apps.personnel.models import Unit
        unit = Unit.objects.filter(pk=data['unit'], is_active=True).first() or unit
    if unit is None:
        raise ValidationError({'unit': 'Your account has no unit — an administrator must assign you to a unit first.'})

    mission = _resolve_mission(user, data.get('mission'))
    activity = (data.get('activity_mission') or (mission.name if mission else '')).strip()
    objectives = (data.get('safety_objectives') or '').strip()
    if not activity or not objectives:
        raise ValidationError({'detail': 'Activity/Mission and Safety Objectives are required.'})

    imsafe = clean_imsafe(data.get('imsafe'))
    env = clean_environment(data.get('environment'))
    reviewer = _clean_reviewer(user, user, unit, data.get('reviewer'))
    cleaned = _clean_hazard_items(user, unit, data.get('hazards'))

    form = None
    for attempt in range(5):
        try:
            with transaction.atomic():
                form = MRMForm.objects.create(
                    mrm_number=generate_mrm_number(), mission=mission, activity_mission=activity[:255],
                    unit=unit, creator_unit=unit, created_by=user, creator_name=_full_name(user),
                    reviewed_by=reviewer, reviewer_name=_full_name(reviewer), reviewer_unit=reviewer.unit,
                    safety_objectives=objectives, imsafe=imsafe,
                    aircraft_vehicle=(data.get('aircraft_vehicle') or '').strip()[:255],
                    environment_data=env, environment=render_environment(env),
                    mission_statement=(data.get('mission_statement') or '').strip() or DEFAULT_MISSION_STATEMENT,
                )
            break
        except IntegrityError:
            if attempt == 4:
                raise ValidationError({'detail': 'Could not allocate a unique MRM number — please try again.'})

    _apply_hazards(form, cleaned)
    _sync_tagged(form, data.get('tagged_personnel'), user)
    recalculate(form)
    _event(form, MRMEvent.Kind.CREATED, user, mrm_number=form.mrm_number)
    _audit(user, AuditLog.Action.CREATE, form, f'Created MRM {form.mrm_number} "{form.activity_mission}"', request)
    return form


@transaction.atomic
def update_mrm(user, form, data, request=None):
    mode, message = access.edit_mode(form, user)
    if mode is None:
        raise PermissionDenied(message)
    readonly = access.READONLY_FIELDS.get(mode, set())
    changed = []

    def touch(name):
        changed.append(name)

    if 'activity_mission' in data:
        value = (data['activity_mission'] or '').strip()
        if not value:
            raise ValidationError({'activity_mission': 'Activity/Mission is required.'})
        form.activity_mission = value[:255]
        touch('activity_mission')
    if 'safety_objectives' in data:
        value = (data['safety_objectives'] or '').strip()
        if not value:
            raise ValidationError({'safety_objectives': 'Safety Objectives are required.'})
        form.safety_objectives = value
        touch('safety_objectives')
    if 'aircraft_vehicle' in data:
        form.aircraft_vehicle = (data['aircraft_vehicle'] or '').strip()[:255]
        touch('aircraft_vehicle')
    if 'mission_statement' in data:
        form.mission_statement = (data['mission_statement'] or '').strip() or DEFAULT_MISSION_STATEMENT
        touch('mission_statement')
    if 'imsafe' in data:
        form.imsafe = clean_imsafe(data['imsafe'])
        touch('imsafe')
    if 'environment' in data:
        env = clean_environment(data['environment'])
        form.environment_data, form.environment = env, render_environment(env)
        touch('environment')
    if 'mission' in data:
        form.mission = _resolve_mission(user, data['mission'], form=form)
        touch('mission')
    if 'reviewer' in data:
        if 'reviewer' in readonly:
            raise PermissionDenied('The reviewer can no longer be changed at this stage.')
        reviewer = _clean_reviewer(user, form.created_by, form.unit, data['reviewer'])
        form.reviewed_by, form.reviewer_name, form.reviewer_unit = reviewer, _full_name(reviewer), reviewer.unit
        touch('reviewer')

    if 'hazards' in data:
        cleaned = _clean_hazard_items(user, form.unit, data['hazards'], [mh.hazard_id for mh in form.mission_hazards.all()])
        _apply_hazards(form, cleaned)
        touch('hazards')
    if 'tagged_personnel' in data:
        _sync_tagged(form, data['tagged_personnel'], user)
        touch('tagged_personnel')

    if not changed:
        return form

    # Content changed after people signed ⇒ their signatures no longer cover what is on the form.
    signatures_reset = False
    if form.creator_signed or form.evaluator_signed:
        form.creator_signed = form.evaluator_signed = False
        form.creator_signature_date = form.evaluator_signature_date = None
        signatures_reset = True

    form.last_edited = timezone.now()
    form.last_edited_by = user
    form.save()
    recalculate(form)
    _event(form, MRMEvent.Kind.EDITED, user, fields=changed, mode=mode, signatures_reset=signatures_reset)
    _audit(user, AuditLog.Action.UPDATE, form, f'Edited MRM {form.mrm_number} ({mode}): {", ".join(changed)}', request)
    return form


# ---------------------------------------------------------------------------
# mission sync & dashboard alerts
# ---------------------------------------------------------------------------

def sync_mission(form, event, user, comments=''):
    """Mirror the MRM's state onto the linked UOMS Mission so existing mission views/reports stay truthful."""
    mission = form.mission
    if mission is None:
        return
    from apps.missions.models import Mission, MissionApprovalLog

    now = timezone.now()
    R = Mission.RiskReviewStatus
    L = MissionApprovalLog.Action
    if event == 'SUBMITTED':
        mission.risk_review_status, mission.submitted_by, mission.submitted_at = R.SUBMITTED, user, now
        fields, action = ['risk_review_status', 'submitted_by', 'submitted_at'], L.SUBMITTED
    elif event == 'APPROVED':
        # MRM approval is a *risk* decision; whether the mission itself is approved is decided separately by its authority.
        mission.risk_review_status = R.APPROVED
        mission.reviewed_by, mission.reviewed_at, mission.review_comments = user, now, comments
        fields, action = ['risk_review_status', 'reviewed_by', 'reviewed_at', 'review_comments'], L.APPROVED
    elif event in ('REJECTED', 'REOPENED'):
        mission.risk_review_status = R.REJECTED
        mission.reviewed_by, mission.reviewed_at, mission.review_comments = user, now, comments
        fields, action = ['risk_review_status', 'reviewed_by', 'reviewed_at', 'review_comments'], L.REJECTED if event == 'REJECTED' else L.REOPENED
    else:  # 'DRAFT' — the MRM was archived
        mission.risk_review_status = R.DRAFT
        fields, action = ['risk_review_status'], L.REOPENED
    mission.save(update_fields=fields + ['updated_at'])
    MissionApprovalLog.objects.create(mission=mission, action=action, actor=user, comments=f'[MRM {form.mrm_number}] {comments}'.strip())


_ALERT_SEVERITY = {'SQUADRON_COMMANDER': 'MEDIUM', 'DIRECTOR_FOR_OPERATIONS': 'HIGH', 'COMMANDER': 'CRITICAL'}


def _alert_prefix(form):
    return f'[MRM {form.mrm_number}]'


def raise_risk_alert(form):
    """Surface elevated-risk MRMs awaiting a decision on the dashboard's Risk Alerts widget."""
    from apps.risk.models import RiskAlert

    resolve_risk_alerts(form)
    severity = _ALERT_SEVERITY.get(form.authority_level)
    if not severity:
        return
    RiskAlert.objects.create(
        mission=form.mission, severity=severity,
        title=f'{_alert_prefix(form)} {risk.AUTHORITY_LABELS[form.authority_level]}-level risk awaiting approval',
        description=f'{form.activity_mission} — residual risk {form.total_percent:.0f}% ({form.get_authority_level_display()} decision).',
    )


def resolve_risk_alerts(form):
    from apps.risk.models import RiskAlert

    RiskAlert.objects.filter(title__startswith=_alert_prefix(form), is_resolved=False).update(is_resolved=True)


# ---------------------------------------------------------------------------
# submit / review / authority
# ---------------------------------------------------------------------------

def _require_complete(form):
    problems = []
    if not form.safety_objectives or not form.activity_mission:
        problems.append('Activity/Mission and Safety Objectives are required.')
    if not form.reviewed_by_id:
        problems.append('An evaluator must be assigned.')
    if not form.mission_hazards.exists():
        problems.append('At least one hazard must be selected.')
    if not all(form.imsafe.get(k) for k in IMSAFE_CHECKLIST):
        problems.append("All I'M SAFE checklist items must be confirmed.")
    env = form.environment_data or {}
    if not (all(env.get(k) for k in ENVIRONMENT_FIELDS) or (not env and form.environment)):
        problems.append('All environment fields are required.')
    if problems:
        raise ValidationError({'detail': problems})


@transaction.atomic
def submit_mrm(user, form, request=None):
    if not access.can_submit(form, user):
        raise PermissionDenied('Only the creator can submit this MRM, and only while it is a draft or awaiting revision.')
    _require_complete(form)
    resubmission = form.status != MRMForm.Status.DRAFT

    for mh in form.mission_hazards.select_related('hazard'):
        mh.take_snapshot()
        mh.save(update_fields=['snapshot'])
    recalculate(form)

    form.status = MRMForm.Status.SUBMITTED
    form.review_status = MRMForm.ReviewStatus.PENDING
    form.date_submitted = timezone.now()
    form.date_reviewed = None
    form.evaluator_signed, form.evaluator_signature_date = False, None
    form.authority_assigned_to, form.authority_name, form.authority_unit = None, '', None
    signed = bool(user.signature)
    form.creator_signed = signed
    form.creator_signature_date = timezone.now() if signed else None
    form.save()

    sync_mission(form, 'SUBMITTED', user, 'Resubmitted after revision' if resubmission else '')
    raise_risk_alert(form)
    _event(form, MRMEvent.Kind.SUBMITTED, user, resubmission=resubmission, signed=signed)
    _audit(user, AuditLog.Action.OTHER, form, f'Submitted MRM {form.mrm_number} for review', request)
    return form, signed


def find_authority(form):
    """Pick the decision-maker for the form's risk tier (None when nobody holds that designation)."""
    level = form.authority_level
    if level == 'OPERATOR':
        return form.created_by
    if level == 'SUPERVISOR':
        return form.reviewed_by
    # Higher tiers: the nearest holder of the designation in the creator's unit or any mother unit,
    # never the creator or reviewer (separation of duties).
    candidates = access.authority_candidates(
        form.creator_unit or form.unit, level, exclude_user_ids=[form.created_by_id, form.reviewed_by_id],
    )
    return candidates[0] if candidates else None


def _assign(form, authority_user, actor, reason):
    form.authority_assigned_to = authority_user
    form.authority_name = _full_name(authority_user)
    form.authority_unit = authority_user.unit if authority_user else None
    form.authority_approved = False
    form.authority_approval_date = None
    form.save(update_fields=[
        'authority_assigned_to', 'authority_name', 'authority_unit', 'authority_approved',
        'authority_approval_date', 'updated_at',
    ])
    _event(form, MRMEvent.Kind.AUTHORITY_ASSIGNED, actor, assigned_to=authority_user.username if authority_user else None,
           level=form.authority_level, reason=reason)


@transaction.atomic
def review_mrm(user, form, decision, notes='', auto_sign=False, request=None):
    if not access.can_review(form, user):
        raise PermissionDenied('You are not assigned to review this MRM, or it is not awaiting review.')
    R = MRMForm.ReviewStatus
    if decision not in (R.APPROVED, R.REJECTED, R.NEEDS_REVISION):
        raise ValidationError({'review_status': 'Decision must be approved, rejected or needs_revision.'})
    notes = (notes or '').strip()
    if decision != R.APPROVED and not notes:
        raise ValidationError({'review_notes': 'Please explain what must change.'})

    reviewer = form.reviewed_by if access.is_admin(user) and form.reviewed_by_id else user
    form.status = MRMForm.Status.REVIEWED
    form.review_status = decision
    form.review_notes = notes
    form.date_reviewed = timezone.now()
    form.reviewer_name, form.reviewer_unit = _full_name(reviewer), reviewer.unit
    if decision == R.APPROVED and auto_sign and user.signature:
        form.evaluator_signed, form.evaluator_signature_date = True, timezone.now()
    form.save()

    warning = None
    if decision == R.APPROVED:
        _event(form, MRMEvent.Kind.REVIEW_APPROVED, user, notes)
        authority_user = find_authority(form)
        if authority_user:
            _assign(form, authority_user, user, 'automatic')
        else:
            form.authority_assigned_to = None
            form.authority_name = ''
            form.save(update_fields=['authority_assigned_to', 'authority_name', 'updated_at'])
            warning = (f'Approved, but nobody holds the "{risk.AUTHORITY_LABELS[form.authority_level]}" designation '
                       f'in this unit or its mother units. An administrator or Unit Safety Officer must assign a decision authority.')
    else:
        kind = MRMEvent.Kind.REVIEW_REJECTED if decision == R.REJECTED else MRMEvent.Kind.REVIEW_REVISION
        _event(form, kind, user, notes)
        sync_mission(form, 'REJECTED' if decision == R.REJECTED else 'REOPENED', user, notes)
        resolve_risk_alerts(form)

    _audit(user, AuditLog.Action.APPROVE if decision == R.APPROVED else AuditLog.Action.REJECT, form,
           f'Evaluator decision on MRM {form.mrm_number}: {decision}', request)
    return form, warning


@transaction.atomic
def reassign_authority(user, form, new_authority_id=None, request=None):
    if not access.can_reassign_authority(form, user):
        raise PermissionDenied('You cannot (re)assign the decision authority for this MRM.')
    if new_authority_id:
        target = User.objects.filter(pk=new_authority_id, is_active=True).first()
        if target is None:
            raise ValidationError({'authority': 'User not found.'})
        if form.authority_level not in ('OPERATOR', 'SUPERVISOR') and target.mrm_designation != form.authority_level:
            raise ValidationError({'authority': f'{target.username} does not hold the {risk.AUTHORITY_LABELS[form.authority_level]} designation.'})
        if target.pk in (form.created_by_id, form.reviewed_by_id) and form.authority_level not in ('OPERATOR', 'SUPERVISOR'):
            raise ValidationError({'authority': 'The creator or reviewer cannot also be the decision authority.'})
    else:
        target = find_authority(form)
        if target is None:
            raise ValidationError({'authority': f'No active user holds the {risk.AUTHORITY_LABELS[form.authority_level]} designation in this unit or its mother units.'})
    _assign(form, target, user, 'manual reassignment')
    _audit(user, AuditLog.Action.OTHER, form, f'Assigned {target.username} as decision authority for MRM {form.mrm_number}', request)
    return form


@transaction.atomic
def authority_approve(user, form, comments='', request=None):
    if not access.can_authority_approve(form, user):
        raise PermissionDenied('You are not the assigned decision authority for this MRM, or it is not ready for approval.')
    if not user.signature:
        raise ValidationError({'signature': 'Upload your signature before approving MRM forms.'})

    now = timezone.now()
    form.authority_approved = True
    form.authority_approval_date = now
    form.authority_name = form.authority_name or _full_name(user)
    form.authority_unit = form.authority_unit or user.unit
    form.completion_time_seconds = max(int((now - form.created_at).total_seconds()), 0)
    form.save()

    pdf_error = None
    try:
        from .pdf import generate_pdf

        pdf_bytes = generate_pdf(form)
        with transaction.atomic():   # savepoint: a failure here must not poison the approval transaction
            form.approved_pdf.save(f'MRM_{form.mrm_number}.pdf', ContentFile(pdf_bytes), save=True)
    except Exception as exc:  # approval must not fail because a PDF could not be drawn
        logger.exception('PDF generation failed for MRM %s', form.mrm_number)
        pdf_error = str(exc)

    sync_mission(form, 'APPROVED', user, comments or f'Approved as {risk.AUTHORITY_LABELS[form.authority_level]}')
    resolve_risk_alerts(form)
    _event(form, MRMEvent.Kind.AUTHORITY_APPROVED, user, comments, pdf_error=pdf_error)
    _audit(user, AuditLog.Action.APPROVE, form, f'Authorised MRM {form.mrm_number} as {risk.AUTHORITY_LABELS[form.authority_level]}', request)
    return form, pdf_error


@transaction.atomic
def sign_mrm(user, form, request=None):
    which = access.can_sign(form, user)
    if which is None:
        raise PermissionDenied('There is nothing for you to sign on this MRM (or you have not uploaded a signature).')
    now = timezone.now()
    if which == 'creator':
        form.creator_signed, form.creator_signature_date = True, now
    else:
        form.evaluator_signed, form.evaluator_signature_date = True, now
    form.save()
    _event(form, MRMEvent.Kind.SIGNED, user, role=which)
    _audit(user, AuditLog.Action.OTHER, form, f'Signed MRM {form.mrm_number} as {which}', request)
    return form, which


@transaction.atomic
def regenerate_pdf(user, form, request=None):
    if not (access.is_admin(user) or (access.is_uso(user) and form.unit_id in (access.scope_unit_ids(user) or set()))):
        raise PermissionDenied('Only administrators and Unit Safety Officers can regenerate PDFs.')
    if not form.authority_approved:
        raise ValidationError({'detail': 'Only approved MRMs have a stored PDF.'})
    from .pdf import generate_pdf

    if form.approved_pdf:
        form.approved_pdf.delete(save=False)
    form.approved_pdf.save(f'MRM_{form.mrm_number}.pdf', ContentFile(generate_pdf(form)), save=True)
    _event(form, MRMEvent.Kind.PDF, user)
    return form


@transaction.atomic
def archive_mrm(user, form, request=None):
    if not access.can_delete_form(form, user):
        raise PermissionDenied('You do not have permission to delete this MRM.')
    form.is_active = False
    form.save(update_fields=['is_active', 'updated_at'])
    resolve_risk_alerts(form)
    if form.mission_id and not form.authority_approved:
        sync_mission(form, 'DRAFT', user, 'MRM archived')
    _event(form, MRMEvent.Kind.ARCHIVED, user)
    _audit(user, AuditLog.Action.DELETE, form, f'Archived MRM {form.mrm_number}', request)


# ---------------------------------------------------------------------------
# personnel & feedback
# ---------------------------------------------------------------------------

@transaction.atomic
def tag_personnel(user, form, target_id, role='Crew Member', request=None):
    if not access.can_manage_personnel(form, user):
        raise PermissionDenied('You do not have permission to manage personnel for this MRM.')
    target = User.objects.filter(pk=target_id, is_active=True).first()
    if target is None or target.unit_id != form.unit_id:
        raise ValidationError({'user': 'Personnel must be active users in the MRM\'s unit.'})
    tag, created = MRMPersonnel.objects.get_or_create(mrm=form, user=target, defaults={'role': role, 'tagged_by': user})
    if not created:
        if tag.is_active:
            raise ValidationError({'user': 'Personnel already tagged for this MRM.'})
        tag.is_active, tag.role, tag.tagged_by = True, role, user
        tag.save()
    _event(form, MRMEvent.Kind.PERSONNEL, user, action='tagged', user=target.username, role=role)
    return tag


@transaction.atomic
def untag_personnel(user, form, tag_id):
    if not access.can_manage_personnel(form, user):
        raise PermissionDenied('You do not have permission to manage personnel for this MRM.')
    tag = form.tagged_personnel.filter(pk=tag_id, is_active=True).first()
    if tag is None:
        raise ValidationError({'detail': 'Tagged person not found.'})
    tag.is_active = False
    tag.save(update_fields=['is_active', 'updated_at'])
    _event(form, MRMEvent.Kind.PERSONNEL, user, action='untagged', user=tag.user.username)


@transaction.atomic
def close_feedback(user, form):
    if not access.can_manage_personnel(form, user):
        raise PermissionDenied('You do not have permission to close feedback for this MRM.')
    form.feedback_collection_closed = True
    form.save(update_fields=['feedback_collection_closed', 'updated_at'])
    _event(form, MRMEvent.Kind.FEEDBACK_CLOSED, user)


def pending_feedback_reminders(form):
    """Tagged people who have not yet given feedback (powers the 'send reminders' action)."""
    done = set(form.feedback_items.values_list('user_id', flat=True))
    return [tag for tag in form.tagged_personnel.filter(is_active=True).select_related('user') if tag.user_id not in done]


RATING_FIELDS = ('risk_assessment_accuracy', 'hazard_identification_rating', 'mitigation_effectiveness')
TEXT_FIELDS = ('what_went_well', 'what_could_be_improved', 'new_hazards_identified', 'lessons_learned',
               'additional_comments', 'recommended_hazard_description', 'recommended_mitigations')


@transaction.atomic
def submit_feedback(user, form, data):
    if not form.authority_approved:
        raise ValidationError({'detail': 'Feedback can only be given for approved MRMs.'})
    if form.feedback_collection_closed:
        raise ValidationError({'detail': 'Feedback collection for this MRM has been closed.'})
    if form.feedback_items.filter(user=user).exists():
        raise ValidationError({'detail': 'You have already submitted feedback for this MRM.'})
    if not access.can_give_feedback(form, user):
        raise PermissionDenied('You are not authorized to provide feedback for this MRM.')

    values = {}
    for name in RATING_FIELDS:
        try:
            rating = int(data.get(name, 3))
        except (TypeError, ValueError):
            rating = 0
        if not 1 <= rating <= 5:
            raise ValidationError({name: 'Rating must be between 1 and 5.'})
        values[name] = rating
    for name in TEXT_FIELDS:
        values[name] = (data.get(name) or '').strip()
    recommend = bool(data.get('recommend_add_to_hazard_registry'))
    if recommend and not values['recommended_hazard_description']:
        raise ValidationError({'recommended_hazard_description': 'Describe the hazard you recommend adding.'})

    feedback = MRMFeedback.objects.create(
        mrm=form, user=user, recommend_add_to_hazard_registry=recommend,
        is_anonymous=bool(data.get('is_anonymous')), **values,
    )
    for officer in User.objects.filter(is_active=True, mrm_authority=A.UNIT_SAFETY_OFFICER):
        if form.unit_id in access.uso_unit_ids(officer):
            FeedbackNotification.objects.create(feedback=feedback, officer=officer)
    return feedback


@transaction.atomic
def review_feedback(user, feedback, action, notes='', action_taken='', new_hazard=None, request=None):
    if not access.can_review_feedback(feedback, user):
        raise PermissionDenied('You do not have permission to review this feedback.')
    notes = (notes or '').strip()
    now = timezone.now()
    created_hazard = None
    S = MRMFeedback.Status

    if action == 'review':
        feedback.status = S.REVIEWED
    elif action == 'dismiss':
        feedback.status, notes = S.REVIEWED, notes or 'Dismissed - No action required.'
    elif action == 'take_action':
        action_taken = (action_taken or '').strip()
        if not action_taken:
            raise ValidationError({'action_taken': 'Describe the action taken.'})
        feedback.status = S.ACTION_TAKEN
        feedback.action_taken, feedback.action_taken_by, feedback.action_taken_at = action_taken, user, now
        if new_hazard:
            # The legacy app invented 3C/2D ratings here; the reviewer must now assess the hazard explicitly.
            required = ('before_likelihood', 'before_severity', 'after_likelihood', 'after_severity')
            if any(new_hazard.get(k) in (None, '') for k in required):
                raise ValidationError({'new_hazard': 'Provide before/after likelihood and severity for the new hazard.'})
            try:
                created_hazard = Hazard.objects.create(
                    unit=feedback.mrm.unit, created_by=user,
                    activity_code=(new_hazard.get('activity_code') or feedback.mrm.activity_mission)[:100],
                    hazard_description=new_hazard.get('hazard_description') or feedback.recommended_hazard_description or feedback.new_hazards_identified,
                    mitigations=new_hazard.get('mitigations') or feedback.recommended_mitigations or feedback.what_could_be_improved,
                    before_likelihood=new_hazard['before_likelihood'], before_severity=new_hazard['before_severity'],
                    after_likelihood=new_hazard['after_likelihood'], after_severity=new_hazard['after_severity'],
                )
            except risk.RiskInputError as exc:
                raise ValidationError({'new_hazard': str(exc)})
            if not created_hazard.hazard_description or not created_hazard.mitigations:
                raise ValidationError({'new_hazard': 'The new hazard needs a description and mitigations.'})
    else:
        raise ValidationError({'action': 'Action must be review, take_action or dismiss.'})

    feedback.reviewed_by, feedback.reviewed_at, feedback.review_notes = user, now, notes
    feedback.save()
    feedback.notifications.filter(is_read=False).update(is_read=True, read_at=now)
    _audit(user, AuditLog.Action.UPDATE, feedback.mrm, f'Feedback on MRM {feedback.mrm.mrm_number}: {action}', request)
    return feedback, created_hazard


# ---------------------------------------------------------------------------
# account lifecycle support
# ---------------------------------------------------------------------------

def pending_assignments(user):
    """Active MRM forms that are blocked until `user` acts (used by the account-deactivation guard)."""
    R, S = MRMForm.ReviewStatus, MRMForm.Status
    out = []
    for f in MRMForm.objects.filter(is_active=True, reviewed_by=user, status=S.SUBMITTED, review_status=R.PENDING):
        out.append({'mrm_number': f.mrm_number, 'id': str(f.id), 'waiting_on': 'review'})
    for f in MRMForm.objects.filter(is_active=True, authority_assigned_to=user, status=S.REVIEWED,
                                    review_status=R.APPROVED, authority_approved=False):
        out.append({'mrm_number': f.mrm_number, 'id': str(f.id), 'waiting_on': 'approval'})
    return out


@transaction.atomic
def reassign_reviewer(user, form, new_reviewer_id, request=None):
    """Hand a form that is awaiting review to another evaluator (e.g. before the current one is deactivated)."""
    allowed = access.is_admin(user) or (access.is_uso(user) and form.unit_id in (access.scope_unit_ids(user) or set()))
    if not allowed:
        raise PermissionDenied('Only administrators and Unit Safety Officers can reassign the reviewer.')
    if not (form.status == MRMForm.Status.SUBMITTED and form.review_status == MRMForm.ReviewStatus.PENDING):
        raise ValidationError({'detail': 'The reviewer can only be reassigned while the form is awaiting review.'})
    reviewer = _clean_reviewer(user, form.created_by, form.unit, new_reviewer_id)
    previous = form.reviewer_name
    form.reviewed_by, form.reviewer_name, form.reviewer_unit = reviewer, _full_name(reviewer), reviewer.unit
    form.save(update_fields=['reviewed_by', 'reviewer_name', 'reviewer_unit', 'updated_at'])
    _event(form, MRMEvent.Kind.EDITED, user, fields=['reviewer'], reassigned_from=previous, reassigned_to=reviewer.username)
    _audit(user, AuditLog.Action.UPDATE, form, f'Reassigned reviewer of MRM {form.mrm_number} to {reviewer.username}', request)
    return form


# Mission.risk_review_status values that an MRM stage projects onto (the MRM is authoritative).
_STAGE_TO_MISSION_REVIEW = {
    'draft': 'DRAFT', 'awaiting_review': 'SUBMITTED', 'awaiting_authority': 'SUBMITTED',
    'needs_authority_assignment': 'SUBMITTED', 'needs_revision': 'REJECTED', 'rejected': 'REJECTED', 'approved': 'APPROVED',
}


def expected_mission_review_status(form):
    from .serializers import stage_of

    return _STAGE_TO_MISSION_REVIEW[stage_of(form)]
