"""
MRM authority & visibility rules.

These port the legacy decorators (admin/evaluator/creator/unit_safety_officer_required),
the per-role unit scoping of the MRM list, and services/edit_permissions.py — keeping the
same authority model — with the legacy gaps closed (see the migration notes in README_MRM.md).

Authority recap (User.mrm_authority; UOMS ADMIN role always acts as ADMINISTRATOR):

  ADMINISTRATOR        everything, all units
  UNIT_SAFETY_OFFICER  oversight of assigned units (+ their sub-units): read forms, manage the
                       hazard registry, review feedback, scoped user admin, analytics
  EVALUATOR            create forms, review forms assigned to them, manage own-unit hazards
  CREATOR              create/submit own forms, read own-unit hazards
  (blank)              no MRM authority — sees only approved MRMs they are tagged on

A *designation* (Operator … Commander) is independent: it is the decision-authority tier a user
may sign for, regardless of their authority above.
"""
from django.db.models import Q

from apps.accounts.models import User
from apps.personnel.models import Unit

A = User.MRMAuthority


def authority(user):
    return user.effective_mrm_authority if user and user.is_authenticated else ''


def is_admin(user):
    return authority(user) == A.ADMINISTRATOR


def is_uso(user):
    return authority(user) == A.UNIT_SAFETY_OFFICER


def is_evaluator(user):
    return authority(user) == A.EVALUATOR


def can_author(user):
    """Create/submit MRM forms (legacy `creator_required`)."""
    return authority(user) in (A.ADMINISTRATOR, A.EVALUATOR, A.CREATOR)


def can_manage_registry(user):
    """Create/edit/delete hazards (legacy: Administrator, Evaluator, Unit Safety Officer)."""
    return authority(user) in (A.ADMINISTRATOR, A.EVALUATOR, A.UNIT_SAFETY_OFFICER)


# ---------------------------------------------------------------------------
# Unit scope
# ---------------------------------------------------------------------------

def uso_unit_ids(user):
    """Units a Unit Safety Officer oversees: every assignment (and the home unit) plus all sub-units."""
    roots = set(user.safety_assignments.filter(is_active=True).values_list('unit_id', flat=True))
    if user.unit_id:
        roots.add(user.unit_id)
    ids = set()
    for unit in Unit.objects.filter(id__in=roots):
        ids |= unit.get_descendant_ids(include_self=True)
    return ids


def scope_unit_ids(user):
    """
    Unit ids the user may *manage* data for, or None meaning "all units".
    Evaluators/Creators are deliberately limited to their own unit (no sub-units), as in the legacy system.
    """
    if is_admin(user):
        return None
    if is_uso(user):
        return uso_unit_ids(user)
    return {user.unit_id} if user.unit_id else set()


def unit_in_scope(user, unit_id):
    scope = scope_unit_ids(user)
    return scope is None or unit_id in scope


def ancestor_units(unit):
    """Parent chain, nearest first (excludes the unit itself)."""
    chain, seen, current = [], {unit.id}, unit.parent_unit
    while current and current.id not in seen:
        chain.append(current)
        seen.add(current.id)
        current = current.parent_unit
    return chain


# ---------------------------------------------------------------------------
# Visibility
# ---------------------------------------------------------------------------

def involvement_q(user):
    """Forms a user is directly part of: made, reviewing, deciding, or (once approved) tagged on."""
    return (
        Q(created_by=user)
        | Q(reviewed_by=user)
        | Q(authority_assigned_to=user)
        | Q(tagged_personnel__user=user, tagged_personnel__is_active=True, authority_approved=True)
    )


def visible_forms(user, queryset=None):
    from .models import MRMForm

    qs = queryset if queryset is not None else MRMForm.objects.all()
    qs = qs.filter(is_active=True)
    if is_admin(user) or user.role == User.Role.COMMANDER:
        # UOMS commanders keep read-only oversight of every unit, consistent with the other modules.
        return qs
    if is_uso(user):
        return qs.filter(Q(unit_id__in=uso_unit_ids(user)) | involvement_q(user)).distinct()
    return qs.filter(involvement_q(user)).distinct()


def can_view_form(user, form):
    return visible_forms(user).filter(pk=form.pk).exists()


def visible_hazards(user, queryset=None):
    """Hazard-registry rows the user can see: all (admin) or their unit(s) — USOs see every unit they oversee."""
    from .models import Hazard

    qs = queryset if queryset is not None else Hazard.objects.all()
    qs = qs.filter(is_active=True)
    scope = scope_unit_ids(user)
    if scope is None or user.role == User.Role.COMMANDER:
        return qs  # UOMS commanders keep read-only oversight of every unit's registry
    return qs.filter(unit_id__in=scope)


def pickable_hazards(user, unit):
    """
    Hazards a form for `unit` may select: that unit's own registry plus every mother unit's
    (a Wing's hazard library is inherited by its Groups/Squadrons).
    """
    from .models import Hazard

    ids = {unit.id} | {u.id for u in ancestor_units(unit)}
    return Hazard.objects.filter(is_active=True, unit_id__in=ids)


def can_write_hazard(user, hazard):
    if not can_manage_registry(user):
        return False
    scope = scope_unit_ids(user)
    return scope is None or hazard.unit_id in scope


# ---------------------------------------------------------------------------
# Form-level permissions (port of services/edit_permissions.py + route checks)
# ---------------------------------------------------------------------------

def edit_mode(form, user):
    """Returns (mode, message). mode is None when the user may not edit."""
    if form.authority_approved:
        return None, 'MRM has been approved and cannot be edited.'
    if is_admin(user):
        return 'admin', 'Administrator edit mode'
    if form.created_by_id == user.id:
        if form.status == form.Status.DRAFT:
            return 'creator_draft', 'Editing your draft MRM'
        if form.status == form.Status.SUBMITTED and form.review_status == form.ReviewStatus.PENDING:
            return 'creator_submitted', 'Editing your submitted MRM before review'
        if form.status == form.Status.REVIEWED and form.review_status in (
            form.ReviewStatus.REJECTED, form.ReviewStatus.NEEDS_REVISION,
        ):
            return 'creator_revision', 'Revising your MRM after evaluator feedback'
        return None, 'Your MRM is being reviewed and cannot be edited.'
    if is_evaluator(user) and form.reviewed_by_id == user.id and form.status in (
        form.Status.DRAFT, form.Status.SUBMITTED,
    ):
        return 'evaluator', 'Reviewing and editing assigned MRM'
    return None, 'You do not have permission to edit this MRM.'


# Fields each edit mode may NOT change (the legacy get_readonly_fields()).
READONLY_FIELDS = {
    'creator_draft': {'mrm_number'},
    'creator_submitted': {'mrm_number', 'reviewer'},
    'creator_revision': {'mrm_number'},
    'evaluator': {'mrm_number', 'created_by', 'reviewer'},
    'admin': set(),
}


def can_delete_form(form, user):
    if is_admin(user):
        return True
    return form.created_by_id == user.id and form.status == form.Status.DRAFT and not form.authority_approved


def can_submit(form, user):
    if form.created_by_id != user.id or form.authority_approved:
        return False
    if form.status == form.Status.DRAFT:
        return True
    return form.status == form.Status.REVIEWED and form.review_status in (
        form.ReviewStatus.REJECTED, form.ReviewStatus.NEEDS_REVISION,
    )


def can_review(form, user):
    if not (is_admin(user) or (is_evaluator(user) and form.reviewed_by_id == user.id)):
        return False
    return form.status == form.Status.SUBMITTED and form.review_status == form.ReviewStatus.PENDING


def can_authority_approve(form, user):
    return (
        form.authority_assigned_to_id == user.id
        and form.status == form.Status.REVIEWED
        and form.review_status == form.ReviewStatus.APPROVED
        and not form.authority_approved
    )


def can_reassign_authority(form, user):
    if form.authority_approved or not (
        form.status == form.Status.REVIEWED and form.review_status == form.ReviewStatus.APPROVED
    ):
        return False
    if is_admin(user):
        return True
    return is_uso(user) and form.unit_id in (scope_unit_ids(user) or set())


def can_reassign_reviewer(form, user):
    if not (form.status == form.Status.SUBMITTED and form.review_status == form.ReviewStatus.PENDING):
        return False
    return is_admin(user) or (is_uso(user) and form.unit_id in (scope_unit_ids(user) or set()))


def can_manage_personnel(form, user):
    if is_admin(user) or form.created_by_id == user.id or form.reviewed_by_id == user.id:
        return True
    return is_uso(user) and form.unit_id in (scope_unit_ids(user) or set())


def can_sign(form, user):
    """Which signature (if any) the user could apply right now."""
    if not user.signature:
        return None
    if form.created_by_id == user.id and form.status != form.Status.DRAFT and not form.creator_signed:
        return 'creator'
    if (
        form.reviewed_by_id == user.id and form.status == form.Status.REVIEWED
        and form.review_status == form.ReviewStatus.APPROVED and not form.evaluator_signed
    ):
        return 'evaluator'
    return None


def is_tagged(form, user):
    return form.tagged_personnel.filter(user=user, is_active=True).exists()


def can_give_feedback(form, user):
    if not form.authority_approved or form.feedback_collection_closed:
        return False
    if form.feedback_items.filter(user=user).exists():
        return False
    return is_tagged(form, user) or is_admin(user) or form.reviewed_by_id == user.id


def can_review_feedback(feedback, user):
    form = feedback.mrm
    if is_admin(user) or (is_evaluator(user) and form.reviewed_by_id == user.id):
        return True
    return is_uso(user) and form.unit_id in (scope_unit_ids(user) or set())


# ---------------------------------------------------------------------------
# People pickers
# ---------------------------------------------------------------------------

def _units_chain(unit):
    return [unit] + ancestor_units(unit) if unit else []


def evaluator_candidates(unit, exclude_user=None):
    """Active evaluators in the unit or any mother unit (nearest first). The creator can never review their own form."""
    chain = _units_chain(unit)
    users = list(
        User.objects.filter(is_active=True, mrm_authority=A.EVALUATOR, unit__in=chain)
        .exclude(pk=getattr(exclude_user, 'pk', None))
    )
    rank = {u.id: i for i, u in enumerate(chain)}
    users.sort(key=lambda u: (rank.get(u.unit_id, 99), u.username))
    return users


def authority_candidates(unit, designation, exclude_user_ids=()):
    """Active users holding the designation, nearest unit first, excluding creator/reviewer (separation of duties)."""
    chain = _units_chain(unit)
    users = list(
        User.objects.filter(is_active=True, mrm_designation=designation, unit__in=chain)
        .exclude(pk__in=[i for i in exclude_user_ids if i])
    )
    rank = {u.id: i for i, u in enumerate(chain)}
    users.sort(key=lambda u: (rank.get(u.unit_id, 99), u.username))
    return users
