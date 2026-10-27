"""
Security-sensitive account policy shared by every code path that can change a user
(User Management API, the MRM Safety Office, management commands).

* SECURITY_FIELDS changes are always audited with before/after values.
* A user cannot be deactivated while MRM work is waiting on them (a form they must
  review or approve) — otherwise those forms would be stranded with no actor.
"""
from rest_framework.exceptions import ValidationError

SECURITY_FIELDS = ('role', 'unit_id', 'section_id', 'mrm_authority', 'mrm_designation', 'is_active', 'is_superuser')


def snapshot(user):
    return {name: ('' if getattr(user, name) is None else str(getattr(user, name))) for name in SECURITY_FIELDS}


def changes(before, after):
    return {name: {'from': before[name], 'to': after[name]} for name in SECURITY_FIELDS if before[name] != after[name]}


def deactivation_blockers(user):
    """MRM forms that cannot proceed without this user (empty list = safe to deactivate)."""
    from apps.mrm.services import pending_assignments

    return pending_assignments(user)


def assert_can_deactivate(user, acting_user=None):
    if acting_user is not None and acting_user.pk == user.pk:
        raise ValidationError({'detail': 'You cannot deactivate your own account.'})
    blockers = deactivation_blockers(user)
    if blockers:
        listing = ', '.join(f'{b["mrm_number"]} ({b["waiting_on"]})' for b in blockers[:10])
        more = f' and {len(blockers) - 10} more' if len(blockers) > 10 else ''
        raise ValidationError({
            'detail': (f'{user.username} still has MRM forms waiting on them: {listing}{more}. '
                       'Reassign the reviewer/approver on each form first (MRM form → Assign approver / Reassign reviewer).'),
            'blocking_forms': [b['mrm_number'] for b in blockers],
        })
