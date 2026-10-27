"""
Custom User model for UOMS.

The `role` field drives role-based access control (RBAC) throughout the
system (see apps.core.permissions). A user's role is distinct from the
personnel `Position`/`Rank` fields defined in apps.personnel — role is
"what can this account do in the system", while rank/position are
military/organizational attributes tracked in the Personnel Management
module.
"""
import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.accounts.managers import UserManager


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'System Administrator'
        COMMANDER = 'COMMANDER', 'Unit Commander'
        STAFF = 'STAFF', 'Staff Officer'
        OPERATOR = 'OPERATOR', 'Operator / Data Entry'
        VIEWER = 'VIEWER', 'Read-only Viewer'

    class MRMAuthority(models.TextChoices):
        """
        Authority within the Mission Risk Management (MRM) workflow, carried over
        unchanged from the legacy MRM system. Independent of `role`: `role` gates
        the UOMS modules, `mrm_authority` gates what a user may do to MRM forms
        and the hazard registry (see apps.mrm.access).
        """
        ADMINISTRATOR = 'ADMINISTRATOR', 'Administrator'
        EVALUATOR = 'EVALUATOR', 'Evaluator'
        CREATOR = 'CREATOR', 'Creator'
        UNIT_SAFETY_OFFICER = 'UNIT_SAFETY_OFFICER', 'Unit Safety Officer'

    class MRMDesignation(models.TextChoices):
        """Mission decision-authority tier a user can sign for (matched to MRM risk %)."""
        OPERATOR = 'OPERATOR', 'Operator'
        SUPERVISOR = 'SUPERVISOR', 'Supervisor'
        SQUADRON_COMMANDER = 'SQUADRON_COMMANDER', 'Squadron Commander'
        DIRECTOR_FOR_OPERATIONS = 'DIRECTOR_FOR_OPERATIONS', 'Director for Operations'
        COMMANDER = 'COMMANDER', 'Commander'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.VIEWER)
    unit = models.ForeignKey(
        'personnel.Unit', null=True, blank=True, on_delete=models.SET_NULL, related_name='users',
        help_text='Assigned organizational unit/AOR — drives unit-based data scoping.',
    )
    section = models.ForeignKey(
        'personnel.Section', null=True, blank=True, on_delete=models.SET_NULL, related_name='users',
        help_text='Assigned section within the unit.',
    )
    unit_legacy = models.CharField(
        max_length=150, blank=True,
        help_text='Deprecated free-text unit value from before unit became a real relation. '
                   'Kept for reference; use `unit` going forward. See migrate_user_units command.',
    )
    phone_number = models.CharField(max_length=30, blank=True)
    mrm_authority = models.CharField(
        max_length=30, choices=MRMAuthority.choices, blank=True,
        help_text='MRM workflow authority. Blank = no MRM authority (can only see MRMs they are tagged on). '
                  'System Administrators always act as MRM Administrators.',
    )
    mrm_designation = models.CharField(
        max_length=30, choices=MRMDesignation.choices, blank=True,
        help_text='Decision-authority tier this user may approve MRMs for.',
    )
    signature = models.ImageField(
        upload_to='mrm/signatures/', null=True, blank=True,
        help_text='Handwritten signature image used on MRM forms.',
    )
    must_change_password = models.BooleanField(default=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    REQUIRED_FIELDS = ['email']

    class Meta:
        ordering = ['username']
        indexes = [
            models.Index(fields=['role']),
            models.Index(fields=['unit']),
            models.Index(fields=['section']),
        ]

    def __str__(self):
        return f'{self.username} ({self.get_role_display()})'

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'.strip() or self.username

    @property
    def effective_mrm_authority(self):
        """UOMS system administrators always hold Administrator authority in the MRM workflow."""
        if self.is_superuser or self.role == self.Role.ADMIN:
            return self.MRMAuthority.ADMINISTRATOR
        return self.mrm_authority

    @property
    def rank_abbreviation(self):
        """Rank from the linked Personnel record (if any) — used on MRM forms."""
        record = getattr(self, 'personnel_record', None)
        return record.rank.abbreviation if record and record.rank_id else ''

    @property
    def display_name_with_rank(self):
        return f'{self.rank_abbreviation} {self.full_name}'.strip()
