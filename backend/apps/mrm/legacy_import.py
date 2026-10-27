"""
One-off migration of the legacy Flask MRM database into UOMS.

Reads rows through a small `source` object (so it can be driven from PostgreSQL, from JSON
exports, or from test fixtures) and writes UOMS/MRM models. It is idempotent: users and units are
matched by username / name, hazards, forms and feedback by their stored ``legacy_id``.

Principles
----------
* Never overwrite an existing UOMS account's role, unit or password — only fill blanks.
* Approved MRMs keep the numbers they were approved with. Risk is recomputed with the official
  matrix only for forms that are not yet approved; for approved forms any difference is *reported*
  for safety review rather than silently rewritten.
* Passwords: PBKDF2 hashes are converted losslessly so people keep their password; anything else
  (werkzeug scrypt) becomes an unusable password + must_change_password.
"""
import base64
import json
import logging
import re
from datetime import timezone as dt_timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.dateparse import parse_datetime
from django.utils import timezone

from apps.accounts.models import User
from apps.personnel.models import Personnel, Rank, Unit

from . import risk
from .constants import IMSAFE_CHECKLIST
from .models import (
    FeedbackNotification, Hazard, MissionHazard, MRMEvent, MRMFeedback, MRMForm, MRMPersonnel,
    SafetyOfficerAssignment, UnitLogo,
)

logger = logging.getLogger(__name__)
A, D = User.MRMAuthority, User.MRMDesignation

AUTHORITY_MAP = {
    'administrator': A.ADMINISTRATOR, 'evaluator': A.EVALUATOR, 'creator': A.CREATOR,
    'unit safety officer': A.UNIT_SAFETY_OFFICER,
}
ROLE_FOR_AUTHORITY = {
    A.ADMINISTRATOR: User.Role.ADMIN, A.UNIT_SAFETY_OFFICER: User.Role.STAFF,
    A.EVALUATOR: User.Role.STAFF, A.CREATOR: User.Role.OPERATOR,
}
DESIGNATION_MAP = {
    'operator': D.OPERATOR, 'supervisor': D.SUPERVISOR, 'squadron commander': D.SQUADRON_COMMANDER,
    'director for operations': D.DIRECTOR_FOR_OPERATIONS, 'commander': D.COMMANDER,
}
CATEGORY_MAP = {'hpaf': 'HPAF', 'command': 'COMMAND', 'wing': 'WING', 'group': 'GROUP', 'center': 'GROUP', 'squadron': 'SQUADRON'}
STATUS_MAP = {'draft', 'submitted', 'reviewed'}
REVIEW_MAP = {'pending', 'approved', 'rejected', 'needs_revision'}


class DictSource:
    """Rows supplied as {table_name: [row_dict, …]} (JSON exports, tests)."""

    def __init__(self, tables):
        self.tables = tables

    @classmethod
    def from_json_dir(cls, directory):
        tables = {}
        for path in Path(directory).glob('*.json'):
            tables[path.stem] = json.loads(path.read_text(encoding='utf-8'))
        return cls(tables)

    def rows(self, table):
        return list(self.tables.get(table, []))


class PostgresSource:
    def __init__(self, dsn):
        import psycopg
        from psycopg.rows import dict_row

        self._conn = psycopg.connect(dsn, row_factory=dict_row)

    def rows(self, table):
        import psycopg

        try:
            with self._conn.cursor() as cur:
                cur.execute(f'SELECT * FROM "{table}"')  # table names are fixed literals below
                return list(cur.fetchall())
        except psycopg.errors.UndefinedTable:
            self._conn.rollback()
            return []


def convert_password_hash(legacy):
    """werkzeug 'pbkdf2:sha256:<iter>$<salt>$<hexdigest>' → Django 'pbkdf2_sha256$<iter>$<salt>$<b64>'."""
    match = re.fullmatch(r'pbkdf2:sha256:(\d+)\$([^$]+)\$([0-9a-f]+)', legacy or '')
    if not match:
        return None
    iterations, salt, hexdigest = match.groups()
    return f'pbkdf2_sha256${iterations}${salt}${base64.b64encode(bytes.fromhex(hexdigest)).decode()}'


PH_TZ = ZoneInfo('Asia/Manila')


def _aware(value, tz=PH_TZ):
    """
    The legacy DB stores naive datetimes. Workflow timestamps were written with get_ph_time(), so they
    are Philippine local time; only `date_created` used datetime.utcnow (pass tz=UTC for that one).
    """
    if value is None or value == '':
        return None
    if isinstance(value, str):
        value = parse_datetime(value)
        if value is None:
            return None
    if timezone.is_naive(value):
        value = timezone.make_aware(value, tz)
    return value


def _truthy(value):
    return str(value).strip().lower() in ('1', 'true', 't', 'on', 'yes', 'y')


def _parse_imsafe(raw):
    if not raw:
        return {}
    data = raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except ValueError:
            return {}
    if not isinstance(data, dict):
        return {}
    upper = {str(k).strip().upper()[:1]: v for k, v in data.items()}
    return {key: _truthy(upper.get(key)) for key in IMSAFE_CHECKLIST}


class FlaskImporter:
    def __init__(self, source, static_dir=None, signatures_dir=None, pdf_dir=None, create_units=True,
                 create_personnel=True, dry_run=False, log=print, identity_map=None, trust_usernames=False):
        self.src = source
        self.static_dir = Path(static_dir) if static_dir else None
        self.signatures_dir = Path(signatures_dir) if signatures_dir else None
        self.pdf_dir = Path(pdf_dir) if pdf_dir else None
        self.create_units = create_units
        self.create_personnel = create_personnel
        self.dry_run = dry_run
        self.log = log
        # {legacy_username: existing UOMS username | 'NEW'} — human decisions for ambiguous accounts
        self.identity_map = {str(k).lower(): v for k, v in (identity_map or {}).items()}
        self.trust_usernames = trust_usernames
        self.unresolved = set()   # legacy user ids that could not be mapped safely
        self.units, self.users, self.hazards, self.forms = {}, {}, {}, {}
        self.report = {
            'units_matched': 0, 'units_created': 0, 'users_matched': 0, 'users_created': 0,
            'passwords_converted': 0, 'passwords_need_reset': 0, 'personnel_created': 0,
            'assignments': 0, 'logos': 0, 'hazards': 0, 'forms': 0, 'forms_skipped': 0, 'feedback': 0,
            'tagged': 0, 'files_missing': [], 'warnings': [], 'risk_discrepancies': [],
            'identity_review': [], 'placeholder_emails': [],
        }

    # ------------------------------------------------------------------
    def run(self):
        with transaction.atomic():
            self._units()
            self._users()
            self._assignments()
            self._logos()
            self._hazards()
            self._forms()
            self._personnel()
            self._feedback()
            if self.dry_run:
                transaction.set_rollback(True)
        return self.report

    def _warn(self, message):
        self.report['warnings'].append(message)

    def _file(self, base, name, kind):
        if not (base and name):
            return None
        path = Path(base) / name
        if path.is_file():
            return path
        self.report['files_missing'].append(f'{kind}: {name}')
        return None

    # --- units -----------------------------------------------------------
    def _units(self):
        rows = self.src.rows('units')
        pending_parents = {}
        for row in rows:
            unit = Unit.objects.filter(name__iexact=row['name']).first() or (
                Unit.objects.filter(code__iexact=row.get('acronym') or '').first() if row.get('acronym') else None)
            if unit:
                self.report['units_matched'] += 1
            elif self.create_units:
                code = (row.get('acronym') or row['name'])[:20]
                base, n = code, 1
                while Unit.objects.filter(code=code).exists():
                    n += 1
                    code = f'{base[:17]}-{n}'
                unit = Unit.objects.create(
                    name=row['name'][:150], code=code, is_active=bool(row.get('is_active', True)),
                    category=CATEGORY_MAP.get(str(row.get('category') or '').lower(), 'SQUADRON'),
                )
                self.report['units_created'] += 1
            else:
                self._warn(f'Unit "{row["name"]}" has no UOMS match (use --create-units to create it).')
                continue
            self.units[row['id']] = unit
            if row.get('parent_id'):
                pending_parents[row['id']] = row['parent_id']
        for child_id, parent_id in pending_parents.items():
            child, parent = self.units.get(child_id), self.units.get(parent_id)
            if child and parent and child.parent_unit_id is None and child.pk != parent.pk:
                child.parent_unit = parent
                child.save(update_fields=['parent_unit', 'updated_at'])

    def _unit(self, legacy_id):
        return self.units.get(legacy_id) if legacy_id else None

    def _unit_by_name(self, name):
        return Unit.objects.filter(name__iexact=name).first() if name else None

    # --- users -----------------------------------------------------------
    def _users(self):
        for row in self.src.rows('users'):
            authority = AUTHORITY_MAP.get(str(row.get('authority') or 'Creator').strip().lower(), A.CREATOR)
            designation = DESIGNATION_MAP.get(str(row.get('designation') or '').strip().lower(), '')
            unit = self._unit(row.get('unit_id'))
            verdict, matched, reason = self._resolve_identity(row)
            if verdict == 'ambiguous':
                self.unresolved.add(row['id'])
                self.report['identity_review'].append({
                    'legacy_username': row['username'], 'legacy_email': row.get('email'), 'serial_number': row.get('serial_number'),
                    'reason': reason, 'candidates': [u.username for u in self._candidates(row)],
                    'resolve_with': {row['username']: '<existing UOMS username> or NEW'},
                })
                continue
            user = matched
            if user:
                self.report['users_matched'] += 1
                updates = []
                if not user.mrm_authority and user.role != User.Role.ADMIN:
                    user.mrm_authority = authority
                    updates.append('mrm_authority')
                if not user.mrm_designation and designation:
                    user.mrm_designation = designation
                    updates.append('mrm_designation')
                if user.unit_id is None and unit:
                    user.unit = unit
                    updates.append('unit')
                if updates:
                    user.save(update_fields=updates)
            else:
                real_email = self._real_email(row)
                if not real_email:
                    self.report['placeholder_emails'].append(row['username'])
                user = User(
                    username=row['username'][:150], email=real_email or f'{row["username"]}@mrm-import.invalid',
                    first_name=(row.get('first_name') or '')[:150], last_name=(row.get('last_name') or '')[:150],
                    role=ROLE_FOR_AUTHORITY[authority], unit=unit, mrm_authority=authority,
                    mrm_designation=designation, phone_number=(row.get('contact_number') or '')[:30],
                    is_active=bool(row.get('is_active', True)),
                )
                converted = convert_password_hash(row.get('password_hash'))
                if converted:
                    user.password = converted
                    self.report['passwords_converted'] += 1
                else:
                    user.set_unusable_password()
                    user.must_change_password = True
                    self.report['passwords_need_reset'] += 1
                if authority == A.ADMINISTRATOR:
                    user.role = User.Role.ADMIN
                user.save()
                self.report['users_created'] += 1
            sig = self._file(self.signatures_dir, row.get('signature_filename'), 'signature')
            if sig and not user.signature:
                user.signature.save(sig.name, ContentFile(sig.read_bytes()), save=True)
            user._legacy_row = row  # used by _personnel
            self.users[row['id']] = user

    # --- identity resolution ---------------------------------------------------
    @staticmethod
    def _real_email(row):
        email = (row.get('email') or '').strip().lower()
        return email if email and not email.endswith('.invalid') else ''

    def _candidates(self, row):
        """Existing UOMS accounts that share a *reliable* identifier (email / service number) or the username."""
        found = {}
        email = self._real_email(row)
        if email:
            for u in User.objects.filter(email__iexact=email):
                found[u.pk] = u
        serial = (row.get('serial_number') or '').strip()
        if serial:
            person = Personnel.objects.filter(service_number=serial).select_related('linked_account').first()
            if person and person.linked_account_id:
                found[person.linked_account_id] = person.linked_account
        by_name = User.objects.filter(username__iexact=row['username']).first()
        if by_name:
            found[by_name.pk] = by_name
        return list(found.values())

    def _resolve_identity(self, row):
        """
        ('match', user, '') | ('create', None, '') | ('ambiguous', None, reason).
        Never merges on name similarity. A username alone is accepted only when nothing contradicts it
        (and only with --trust-usernames, or when the UOMS account has no email/personnel evidence to contradict).
        """
        username = row['username']
        decision = self.identity_map.get(username.lower())
        if decision:
            if str(decision).upper() == 'NEW':
                if User.objects.filter(username__iexact=username).exists():
                    return 'ambiguous', None, f'Marked NEW but the username "{username}" is already taken in UOMS — choose another mapping.'
                return 'create', None, ''
            target = User.objects.filter(username__iexact=str(decision)).first()
            if target is None:
                return 'ambiguous', None, f'Mapping target "{decision}" does not exist in UOMS.'
            return 'match', target, ''

        email = self._real_email(row)
        serial = (row.get('serial_number') or '').strip()
        by_email = User.objects.filter(email__iexact=email).first() if email else None
        person = Personnel.objects.filter(service_number=serial).select_related('linked_account').first() if serial else None
        by_serial = person.linked_account if person and person.linked_account_id else None
        by_name = User.objects.filter(username__iexact=username).first()

        strong = {u.pk: u for u in (by_email, by_serial) if u is not None}
        if len(strong) > 1:
            return 'ambiguous', None, 'The email and the service number point to two different UOMS accounts.'
        if len(strong) == 1:
            user = next(iter(strong.values()))
            if by_name and by_name.pk != user.pk:
                return 'ambiguous', None, f'Email/service number match "{user.username}", but the username already belongs to a different account ("{by_name.username}").'
            return 'match', user, ''
        if by_name is None:
            return 'create', None, ''
        # username-only evidence
        existing_email = (by_name.email or '').lower()
        if email and existing_email and existing_email != email and not existing_email.endswith('.invalid'):
            return 'ambiguous', None, f'Username matches "{by_name.username}" but their emails differ ({existing_email} vs {email}).'
        if self.trust_usernames or not (email or serial):
            if self.trust_usernames:
                return 'match', by_name, ''
        return 'ambiguous', None, (
            f'Only the username "{username}" matches an existing account; no email or service number corroborates it. '
            'Confirm they are the same person via --identity-map (or pass --trust-usernames).'
        )

    def _user(self, legacy_id):
        return self.users.get(legacy_id) if legacy_id else None

    # --- personnel records (rank & service number shown on forms) ----------
    def _personnel(self):
        if not self.create_personnel:
            return
        for user in self.users.values():
            row = getattr(user, '_legacy_row', {})
            rank_text, serial = (row.get('rank') or '').strip(), (row.get('serial_number') or '').strip()
            if hasattr(user, 'personnel_record') or not (rank_text and serial and user.unit_id):
                continue
            if Personnel.objects.filter(service_number=serial).exists():
                self._warn(f'Service number {serial} (user {user.username}) already exists — personnel record not created.')
                continue
            rank = (Rank.objects.filter(abbreviation__iexact=rank_text[:20]).first()
                    or Rank.objects.filter(name__iexact=rank_text[:100]).first())
            if rank is None:
                rank = Rank.objects.create(name=rank_text[:100], abbreviation=rank_text[:20], order=999)
            Personnel.objects.create(
                service_number=serial[:30], first_name=(user.first_name or user.username)[:100], last_name=(user.last_name or '-')[:100],
                middle_name=(row.get('middle_name') or '')[:100], rank=rank, unit=user.unit,
                contact_number=user.phone_number, linked_account=user, email='',
            )
            self.report['personnel_created'] += 1
            user.refresh_from_db()

    # --- assignments / logos ------------------------------------------------
    def _assignments(self):
        for row in self.src.rows('unit_assignments'):
            user, unit = self._user(row['user_id']), self._unit(row['unit_id'])
            if user and unit:
                SafetyOfficerAssignment.objects.update_or_create(
                    user=user, unit=unit, defaults={'is_primary': bool(row.get('is_primary')), 'is_active': True})
                self.report['assignments'] += 1

    def _logos(self):
        for row in self.src.rows('unit_logos'):
            unit = self._unit(row.get('unit_id')) or self._unit_by_name(row.get('unit_name'))
            path = self._file(self.static_dir / 'unit_logos' if self.static_dir else None, row.get('logo_filename'), 'unit logo')
            if unit and path:
                logo, _ = UnitLogo.objects.get_or_create(unit=unit, defaults={'uploaded_by': self._user(row.get('uploaded_by'))})
                logo.image.save(path.name, ContentFile(path.read_bytes()), save=True)
                self.report['logos'] += 1

    # --- hazards ------------------------------------------------------------
    def _hazards(self):
        for row in self.src.rows('hazard_registry'):
            unit = self._unit(row.get('unit_id')) or self._unit_by_name(row.get('unit'))
            if unit is None:
                self._warn(f'Hazard #{row["id"]} skipped: unit "{row.get("unit")}" not found.')
                continue
            hazard = Hazard.objects.filter(legacy_id=row['id']).first() or Hazard(legacy_id=row['id'])
            try:
                hazard.unit, hazard.created_by = unit, self._user(row.get('created_by'))
                hazard.activity_code = str(row['activity_code'])[:100]
                hazard.hazard_description = row['hazard_description']
                hazard.mitigations = row.get('mitigations') or ''
                hazard.before_likelihood, hazard.before_severity = row['before_likelihood'], row['before_severity']
                hazard.after_likelihood, hazard.after_severity = row['after_likelihood'], row['after_severity']
                hazard.save()
            except (risk.RiskInputError, KeyError) as exc:
                self._warn(f'Hazard #{row["id"]} skipped: {exc}')
                continue
            self.hazards[row['id']] = hazard
            self.report['hazards'] += 1

    # --- forms --------------------------------------------------------------
    def _forms(self):
        links = {}
        for row in self.src.rows('mission_hazards'):
            if row.get('selected', True) is not False and row.get('selected') != 0:
                links.setdefault(row['mrm_id'], []).append(row)

        for row in self.src.rows('mrm_forms'):
            blocked = [row.get(k) for k in ('created_by', 'reviewed_by', 'authority_assigned_to') if row.get(k) in self.unresolved]
            if blocked:
                self._warn(f'MRM {row["mrm_number"]} skipped: it depends on a user whose identity is unresolved (see identity_review).')
                self.report['forms_skipped'] += 1
                continue
            creator = self._user(row.get('created_by'))
            unit = self._unit(row.get('original_unit_id')) or self._unit_by_name(row.get('original_unit')) or (creator.unit if creator else None)
            if unit is None:
                self._warn(f'MRM {row["mrm_number"]} skipped: cannot determine its unit.')
                self.report['forms_skipped'] += 1
                continue
            if len(str(row['mrm_number'])) > 20:
                self._warn(f'MRM {row["mrm_number"]} skipped: the number is longer than 20 characters.')
                self.report['forms_skipped'] += 1
                continue
            form = MRMForm.objects.filter(legacy_id=row['id']).first()
            if form is None and MRMForm.objects.filter(mrm_number=row['mrm_number']).exists():
                self._warn(f'MRM {row["mrm_number"]} skipped: that number already exists in UOMS.')
                self.report['forms_skipped'] += 1
                continue
            form = form or MRMForm(legacy_id=row['id'], mrm_number=row['mrm_number'])

            approved = bool(row.get('authority_approved'))
            form.unit = unit
            form.creator_unit = self._unit(row.get('original_creator_unit_id')) or unit
            form.reviewer_unit = self._unit(row.get('original_reviewer_unit_id'))
            form.authority_unit = self._unit(row.get('original_authority_unit_id'))
            form.activity_mission = (row.get('activity_mission') or '')[:255]
            form.created_by, form.reviewed_by = creator, self._user(row.get('reviewed_by'))
            form.authority_assigned_to, form.last_edited_by = self._user(row.get('authority_assigned_to')), self._user(row.get('last_edited_by'))
            form.creator_name = (row.get('creator_name') or (creator.display_name_with_rank if creator else ''))[:350]
            form.reviewer_name = (row.get('reviewer_name') or (form.reviewed_by.display_name_with_rank if form.reviewed_by else ''))[:350]
            form.authority_name = (row.get('authority_name') or (form.authority_assigned_to.display_name_with_rank if form.authority_assigned_to else ''))[:350]
            form.safety_objectives = row.get('safety_objectives') or ''
            form.imsafe = _parse_imsafe(row.get('imsafes'))
            form.aircraft_vehicle = (row.get('aircraft_vehicle') or '')[:255]
            form.environment = row.get('environment') or ''
            form.environment_data = {}
            form.mission_statement = row.get('mission_statement') or ''
            status = str(row.get('status') or 'draft').lower()
            form.status = status if status in STATUS_MAP else 'draft'
            review = str(row.get('review_status') or 'pending').lower()
            form.review_status = review if review in REVIEW_MAP else 'pending'
            form.date_submitted, form.date_reviewed = _aware(row.get('date_submitted')), _aware(row.get('date_reviewed'))
            form.review_notes = row.get('review_notes') or ''
            form.creator_signed, form.creator_signature_date = bool(row.get('creator_signed')), _aware(row.get('creator_signature_date'))
            form.evaluator_signed, form.evaluator_signature_date = bool(row.get('evaluator_signed')), _aware(row.get('evaluator_signature_date'))
            form.authority_approved = approved
            form.authority_approval_date = _aware(row.get('authority_approval_date') or row.get('date_approved'))
            form.completion_time_seconds = row.get('completion_time_seconds')
            form.last_edited = _aware(row.get('last_edited'))
            form.feedback_deadline = _aware(row.get('feedback_deadline'))
            form.feedback_collection_closed = bool(row.get('feedback_collection_closed'))
            form.debrief_date = _aware(row.get('debrief_date'))
            form.lessons_learned_summary = row.get('lessons_learned_summary') or ''
            form.is_active = True
            form.save()
            created_at = _aware(row.get('date_created'), dt_timezone.utc)
            if created_at:
                MRMForm.objects.filter(pk=form.pk).update(created_at=created_at)

            self._form_hazards(form, links.get(row['id'], []))
            self._form_risk(form, row, approved)
            self._form_pdf(form, row)

            history = row.get('edit_history')
            if not form.events.exists():
                MRMEvent.objects.create(
                    mrm=form, kind=MRMEvent.Kind.CREATED, actor=creator, actor_name=form.creator_name,
                    metadata={'imported_from': 'flask-mrm', 'legacy_edit_history': history if history else None},
                )
            self.forms[row['id']] = form
            self.report['forms'] += 1

    def _form_hazards(self, form, rows):
        keep = set()
        for position, link in enumerate(rows):
            hazard = self.hazards.get(link['hazard_id'])
            if hazard is None:
                self._warn(f'MRM {form.mrm_number}: hazard #{link["hazard_id"]} missing — line skipped.')
                continue
            mh, _ = MissionHazard.objects.get_or_create(mrm=form, hazard=hazard)
            likelihood, severity = link.get('override_likelihood'), (link.get('override_severity') or '').strip().upper()
            mh.override_likelihood, mh.override_severity = (None, '')
            if likelihood and severity:
                try:
                    likelihood, severity = risk.normalize(likelihood, severity)
                    if risk.rating(likelihood, severity) != hazard.after_risk_rating:
                        mh.override_likelihood, mh.override_severity = likelihood, severity
                except risk.RiskInputError:
                    self._warn(f'MRM {form.mrm_number}: invalid override ignored on hazard #{hazard.legacy_id}.')
            mh.additional_mitigations = link.get('additional_mitigations') or ''
            mh.position = position
            mh.take_snapshot()
            mh.save()
            keep.add(hazard.pk)
        form.mission_hazards.exclude(hazard_id__in=keep).delete()

    def _form_risk(self, form, row, approved):
        hazards = list(form.mission_hazards.select_related('hazard'))
        official = risk.summarize(mh.effective_residual for mh in hazards)
        legacy_level = AUTHORITY_TIER_BY_LABEL.get(str(row.get('authority_level') or '').strip().lower())
        if approved and legacy_level:
            # Keep what the approver actually signed off on …
            form.max_risk, form.residual_risk = row.get('max_risk') or official.max_risk, row.get('residual_risk') or official.residual_risk
            form.total_percent = row.get('total_percent') if row.get('total_percent') is not None else official.total_percent
            form.authority_level = legacy_level
            form.risk_category = row.get('risk_category') or official.risk_category
            # … but flag it when the official matrix would have escalated further.
            order = [code for _, code in risk.AUTHORITY_TIERS]
            if order.index(official.authority_level) > order.index(legacy_level):
                self.report['risk_discrepancies'].append({
                    'mrm_number': form.mrm_number, 'approved_as': risk.AUTHORITY_LABELS[legacy_level],
                    'official_matrix_requires': risk.AUTHORITY_LABELS[official.authority_level],
                    'legacy_percent': form.total_percent, 'official_percent': official.total_percent,
                })
        else:
            form.max_risk, form.residual_risk = official.max_risk, official.residual_risk
            form.total_percent, form.authority_level, form.risk_category = official.total_percent, official.authority_level, official.risk_category
        form.save(update_fields=['max_risk', 'residual_risk', 'total_percent', 'authority_level', 'risk_category'])

    def _form_pdf(self, form, row):
        name = row.get('approved_pdf_filename')
        path = self._file(self.pdf_dir, name, 'approved PDF')
        if path and not form.approved_pdf:
            form.approved_pdf.save(path.name, ContentFile(path.read_bytes()), save=True)

    # --- tagged personnel / feedback ------------------------------------------
    def _feedback(self):
        for row in self.src.rows('mrm_personnel'):
            form, user = self.forms.get(row['mrm_id']), self._user(row['user_id'])
            if form and user:
                MRMPersonnel.objects.update_or_create(
                    mrm=form, user=user,
                    defaults={'role': (row.get('role') or 'Crew Member')[:100], 'tagged_by': self._user(row.get('tagged_by')),
                              'is_active': bool(row.get('is_active', True))})
                self.report['tagged'] += 1

        feedback_map = {}
        for row in self.src.rows('mrm_feedback'):
            form, user = self.forms.get(row['mrm_id']), self._user(row['user_id'])
            if not (form and user):
                continue
            fb = MRMFeedback.objects.filter(legacy_id=row['id']).first() or MRMFeedback.objects.filter(mrm=form, user=user).first() or MRMFeedback(mrm=form, user=user)
            fb.legacy_id = row['id']
            for name in ('risk_assessment_accuracy', 'hazard_identification_rating', 'mitigation_effectiveness'):
                setattr(fb, name, min(max(int(row.get(name) or 3), 1), 5))
            for name in ('what_went_well', 'what_could_be_improved', 'new_hazards_identified', 'lessons_learned',
                         'additional_comments', 'recommended_hazard_description', 'recommended_mitigations',
                         'review_notes', 'action_taken'):
                setattr(fb, name, row.get(name) or '')
            fb.recommend_add_to_hazard_registry = bool(row.get('recommend_add_to_hazard_registry'))
            fb.is_anonymous = bool(row.get('is_anonymous'))
            fb.status = row.get('status') if row.get('status') in ('pending', 'reviewed', 'action_taken') else 'pending'
            fb.reviewed_by, fb.reviewed_at = self._user(row.get('reviewed_by')), _aware(row.get('reviewed_at'))
            fb.action_taken_by, fb.action_taken_at = self._user(row.get('action_taken_by')), _aware(row.get('action_taken_at'))
            fb.save()
            submitted = _aware(row.get('submitted_at'))
            if submitted:
                MRMFeedback.objects.filter(pk=fb.pk).update(submitted_at=submitted)
            feedback_map[row['id']] = fb
            self.report['feedback'] += 1

        for row in self.src.rows('feedback_notifications'):
            fb, officer = feedback_map.get(row['feedback_id']), self._user(row.get('unit_safety_officer_id'))
            if fb and officer:
                FeedbackNotification.objects.update_or_create(
                    feedback=fb, officer=officer,
                    defaults={'is_read': bool(row.get('is_read')), 'read_at': _aware(row.get('read_at'))})


AUTHORITY_TIER_BY_LABEL = {label.lower(): code for code, label in risk.AUTHORITY_LABELS.items()}
