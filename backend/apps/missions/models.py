"""
Mission Risk Management module — full Phase 3 build-out.

Covers: mission profile, hazards, probability/severity risk assessment
(using a standard 5x4 Risk Assessment Code matrix), existing/additional
controls, residual risk, an approval workflow, and risk monitoring.
"""
import uuid

from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.db import models

from apps.core.models import BaseModel
from apps.personnel.models import Personnel, Section, Unit


class Mission(BaseModel):
    """Mission profile — the parent record for hazard/risk assessment and approval."""

    class Status(models.TextChoices):
        PLANNED = 'PLANNED', 'Planned'
        APPROVED = 'APPROVED', 'Approved'
        ONGOING = 'ONGOING', 'Ongoing'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    class RiskReviewStatus(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        SUBMITTED = 'SUBMITTED', 'Submitted for Approval'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    unit = models.ForeignKey(
        Unit, null=True, blank=True, on_delete=models.SET_NULL, related_name='missions',
        help_text='Owning AOR/unit.',
    )
    mission_commander = models.ForeignKey(
        Personnel, null=True, blank=True, on_delete=models.SET_NULL, related_name='commanded_missions',
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)
    location = gis_models.PointField(geography=True, null=True, blank=True, srid=4326)
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)

    # --- Category-driven mission planning ------------------------------------
    class Category(models.TextChoices):
        AIR_OPERATIONS = 'AIR_OPERATIONS', 'Air Operations'
        GROUND_OPERATIONS = 'GROUND_OPERATIONS', 'Ground Operations'

    class ApprovalStatus(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        PENDING = 'PENDING', 'Pending approval'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    category = models.CharField(
        max_length=30, choices=Category.choices, blank=True, default='',
        help_text='Blank only for missions created before categories existed (legacy).',
    )
    responsible_section = models.ForeignKey(
        Section, null=True, blank=True, on_delete=models.SET_NULL, related_name='responsible_missions',
        help_text='Office/Section Primary Responsible (O/SPR). `unit` is the Unit Primary Responsible (UPR).',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='missions_created',
    )
    mrm_assignee = models.ForeignKey(
        Personnel, null=True, blank=True, on_delete=models.SET_NULL, related_name='mrm_mission_assignments',
        help_text='Personnel responsible for preparing the MRM (must be assigned to the mission).',
    )
    client_request_id = models.UUIDField(
        null=True, blank=True, unique=True,
        help_text='Idempotency token from the client; a repeated create with the same token returns the same mission.',
    )

    # Mission approval by the selected authority — independent of MRM risk review below.
    approval_status = models.CharField(max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.DRAFT)
    approval_authority = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='missions_to_approve',
    )
    approval_submitted_at = models.DateTimeField(null=True, blank=True)
    approval_decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='mission_approval_decisions',
    )
    approval_decided_at = models.DateTimeField(null=True, blank=True)
    approval_comments = models.TextField(blank=True)

    # --- MRM risk-review projection (read-only; owned by apps.mrm) ------------
    risk_review_status = models.CharField(
        max_length=20, choices=RiskReviewStatus.choices, default=RiskReviewStatus.DRAFT
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='mission_risk_submissions',
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='mission_risk_reviews',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_comments = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['risk_review_status']),
            models.Index(fields=['unit']),
            models.Index(fields=['category', 'approval_status']),
            models.Index(fields=['approval_authority', 'approval_status']),
        ]
        constraints = [
            # Categorised missions always carry a coherent schedule (legacy uncategorised rows are exempt).
            models.CheckConstraint(
                check=models.Q(category='') | models.Q(
                    start_date__isnull=False, end_date__isnull=False, end_date__gte=models.F('start_date'),
                ),
                name='mission_schedule_valid_when_categorised',
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def active_mrm(self):
        """The formal MRM form (apps.mrm) for this mission, if one exists — it supersedes quick hazard assessments."""
        return self.mrm_forms.filter(is_active=True).order_by('-created_at').first()

    @property
    def effective_risk_review_status(self):
        """The MRM's state when the mission has one (authoritative); otherwise the legacy stored value."""
        mrm = self.active_mrm
        if mrm is not None:
            from apps.mrm.services import expected_mission_review_status

            return expected_mission_review_status(mrm)
        return self.risk_review_status

    @property
    def effective_risk_review_status_display(self):
        return dict(self.RiskReviewStatus.choices).get(self.effective_risk_review_status, self.effective_risk_review_status)

    @property
    def overall_risk_level(self):
        """Highest initial risk level — taken from the MRM's hazards when the mission has an MRM form."""
        mrm = self.active_mrm
        if mrm is not None and mrm.mission_hazards.exists():
            from apps.mrm import risk as mrm_risk

            ratings = [
                (mh.snapshot or {}).get('before_risk_rating') or mh.hazard.before_risk_rating
                for mh in mrm.mission_hazards.select_related('hazard')
            ]
            return HazardAssessment.highest_level([mrm_risk.level(r) for r in ratings])
        levels = [h.initial_risk_level for h in self.hazard_assessments.filter(is_active=True)]
        return HazardAssessment.highest_level(levels)

    @property
    def overall_residual_risk_level(self):
        mrm = self.active_mrm
        if mrm is not None and mrm.mission_hazards.exists():
            return mrm.risk_summary.uoms_level
        levels = [
            h.residual_risk_level
            for h in self.hazard_assessments.filter(is_active=True)
            if h.residual_risk_level
        ]
        return HazardAssessment.highest_level(levels)


class HazardAssessment(BaseModel):
    """
    A single hazard identified for a mission, assessed via the standard
    Probability x Severity Risk Assessment Code (RAC) matrix, with
    existing/additional controls and a re-assessed residual risk.
    """

    class Category(models.TextChoices):
        WEATHER = 'WEATHER', 'Weather / Environmental'
        MECHANICAL = 'MECHANICAL', 'Mechanical / Equipment Failure'
        HUMAN_ERROR = 'HUMAN_ERROR', 'Human Error'
        ENEMY_ACTION = 'ENEMY_ACTION', 'Enemy / Hostile Action'
        TERRAIN = 'TERRAIN', 'Terrain / Route'
        MEDICAL = 'MEDICAL', 'Medical'
        OTHER = 'OTHER', 'Other'

    class Probability(models.TextChoices):
        FREQUENT = 'FREQUENT', 'Frequent (A)'
        LIKELY = 'LIKELY', 'Likely (B)'
        OCCASIONAL = 'OCCASIONAL', 'Occasional (C)'
        SELDOM = 'SELDOM', 'Seldom (D)'
        UNLIKELY = 'UNLIKELY', 'Unlikely (E)'

    class Severity(models.TextChoices):
        CATASTROPHIC = 'CATASTROPHIC', 'Catastrophic (I)'
        CRITICAL = 'CRITICAL', 'Critical (II)'
        MODERATE = 'MODERATE', 'Moderate (III)'
        NEGLIGIBLE = 'NEGLIGIBLE', 'Negligible (IV)'

    class RiskLevel(models.TextChoices):
        EXTREMELY_HIGH = 'EXTREMELY_HIGH', 'Extremely High'
        HIGH = 'HIGH', 'High'
        MEDIUM = 'MEDIUM', 'Medium'
        LOW = 'LOW', 'Low'

    # Standard DoD-style Risk Assessment Code matrix: [Severity][Probability] -> RiskLevel
    _RAC_MATRIX = {
        Severity.CATASTROPHIC: {
            Probability.FREQUENT: RiskLevel.EXTREMELY_HIGH,
            Probability.LIKELY: RiskLevel.EXTREMELY_HIGH,
            Probability.OCCASIONAL: RiskLevel.HIGH,
            Probability.SELDOM: RiskLevel.HIGH,
            Probability.UNLIKELY: RiskLevel.MEDIUM,
        },
        Severity.CRITICAL: {
            Probability.FREQUENT: RiskLevel.EXTREMELY_HIGH,
            Probability.LIKELY: RiskLevel.HIGH,
            Probability.OCCASIONAL: RiskLevel.HIGH,
            Probability.SELDOM: RiskLevel.MEDIUM,
            Probability.UNLIKELY: RiskLevel.LOW,
        },
        Severity.MODERATE: {
            Probability.FREQUENT: RiskLevel.HIGH,
            Probability.LIKELY: RiskLevel.MEDIUM,
            Probability.OCCASIONAL: RiskLevel.MEDIUM,
            Probability.SELDOM: RiskLevel.LOW,
            Probability.UNLIKELY: RiskLevel.LOW,
        },
        Severity.NEGLIGIBLE: {
            Probability.FREQUENT: RiskLevel.MEDIUM,
            Probability.LIKELY: RiskLevel.LOW,
            Probability.OCCASIONAL: RiskLevel.LOW,
            Probability.SELDOM: RiskLevel.LOW,
            Probability.UNLIKELY: RiskLevel.LOW,
        },
    }

    _LEVEL_RANK = {RiskLevel.LOW: 1, RiskLevel.MEDIUM: 2, RiskLevel.HIGH: 3, RiskLevel.EXTREMELY_HIGH: 4}

    mission = models.ForeignKey(Mission, on_delete=models.CASCADE, related_name='hazard_assessments')
    hazard_description = models.TextField()
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)

    probability = models.CharField(max_length=20, choices=Probability.choices)
    severity = models.CharField(max_length=20, choices=Severity.choices)
    initial_risk_level = models.CharField(max_length=20, choices=RiskLevel.choices, editable=False)

    existing_controls = models.TextField(blank=True)
    additional_controls = models.TextField(blank=True)

    residual_probability = models.CharField(max_length=20, choices=Probability.choices, blank=True)
    residual_severity = models.CharField(max_length=20, choices=Severity.choices, blank=True)
    residual_risk_level = models.CharField(max_length=20, choices=RiskLevel.choices, blank=True, editable=False)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=['mission', 'initial_risk_level']),
            models.Index(fields=['category']),
        ]

    def __str__(self):
        return f'{self.mission.name} — {self.hazard_description[:50]}'

    @classmethod
    def compute_risk_level(cls, probability, severity):
        return cls._RAC_MATRIX[severity][probability]

    @classmethod
    def highest_level(cls, levels):
        levels = [lvl for lvl in levels if lvl]
        if not levels:
            return None
        return max(levels, key=lambda lvl: cls._LEVEL_RANK[lvl])

    def save(self, *args, **kwargs):
        self.initial_risk_level = self.compute_risk_level(self.probability, self.severity)
        if self.residual_probability and self.residual_severity:
            self.residual_risk_level = self.compute_risk_level(self.residual_probability, self.residual_severity)
        else:
            self.residual_risk_level = ''
        super().save(*args, **kwargs)


class MissionApprovalLog(BaseModel):
    """Immutable history of a mission's risk-approval workflow transitions."""

    class Action(models.TextChoices):
        SUBMITTED = 'SUBMITTED', 'Submitted for Approval'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'
        REOPENED = 'REOPENED', 'Reopened for Revision'

    class Workflow(models.TextChoices):
        RISK_REVIEW = 'RISK_REVIEW', 'MRM risk review'
        MISSION_APPROVAL = 'MISSION_APPROVAL', 'Mission approval by authority'

    mission = models.ForeignKey(Mission, on_delete=models.CASCADE, related_name='approval_logs')
    workflow = models.CharField(max_length=20, choices=Workflow.choices, default=Workflow.RISK_REVIEW)
    action = models.CharField(max_length=20, choices=Action.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    comments = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.mission.name}: {self.action} @ {self.created_at:%Y-%m-%d %H:%M}'


# ---------------------------------------------------------------------------
# Ground Operations planning records (structured, relational — no free-text blobs)
# ---------------------------------------------------------------------------

class MissionPersonnel(models.Model):
    """A person from the Personnel Inventory assigned to a mission with a role."""

    class Role(models.TextChoices):
        TEAM_LEADER = 'TEAM_LEADER', 'Team Leader'
        ASSISTANT_TEAM_LEADER = 'ASSISTANT_TEAM_LEADER', 'Assistant Team Leader'
        TEAM_MEMBER = 'TEAM_MEMBER', 'Team Member'
        DRIVER = 'DRIVER', 'Driver'
        OTHER = 'OTHER', 'Other'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mission = models.ForeignKey(Mission, on_delete=models.CASCADE, related_name='personnel_assignments')
    personnel = models.ForeignKey(Personnel, on_delete=models.PROTECT, related_name='mission_assignments')
    role = models.CharField(max_length=30, choices=Role.choices, default=Role.TEAM_MEMBER)
    role_other = models.CharField(max_length=100, blank=True, help_text='Required when role is OTHER.')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        constraints = [
            models.UniqueConstraint(fields=['mission', 'personnel'], name='one_assignment_per_person_per_mission'),
            models.UniqueConstraint(
                fields=['mission'], condition=models.Q(role='TEAM_LEADER'), name='one_team_leader_per_mission',
            ),
            models.CheckConstraint(
                check=~models.Q(role='OTHER') | ~models.Q(role_other=''), name='other_role_needs_description',
            ),
        ]

    def __str__(self):
        return f'{self.mission_id}: {self.personnel_id} as {self.role}'

    @property
    def role_label(self):
        return self.role_other if self.role == self.Role.OTHER and self.role_other else self.get_role_display()


class MissionVehicle(models.Model):
    """
    A vehicle used by a mission: either an official fleet vehicle (`vehicle`) or a Privately Owned Vehicle (POV).

    POVs deliberately have no link to the fleet `Vehicle` table and no odometer fields, so a POV can never
    create or alter an official odometer record. This is also **not** a `vehicles.Trip` (the executed-trip log
    with odometer readings): it is the *plan* for the mission.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mission = models.ForeignKey(Mission, on_delete=models.CASCADE, related_name='vehicle_assignments')
    vehicle = models.ForeignKey('vehicles.Vehicle', null=True, blank=True, on_delete=models.PROTECT, related_name='mission_assignments')
    is_pov = models.BooleanField(default=False)
    pov_plate_number = models.CharField(max_length=20, blank=True)
    pov_vehicle_type = models.CharField(max_length=100, blank=True)
    pov_make = models.CharField(max_length=100, blank=True)
    pov_model = models.CharField(max_length=100, blank=True)
    pov_color = models.CharField(max_length=50, blank=True)
    pov_owner_name = models.CharField(max_length=150, blank=True)
    pov_description = models.TextField(blank=True)
    driver = models.ForeignKey(Personnel, null=True, blank=True, on_delete=models.SET_NULL, related_name='driven_mission_vehicles')
    sequence = models.PositiveSmallIntegerField(default=1)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sequence', 'created_at']
        constraints = [
            models.CheckConstraint(
                check=(models.Q(is_pov=False, vehicle__isnull=False, pov_plate_number='')
                       | models.Q(is_pov=True, vehicle__isnull=True) & ~models.Q(pov_plate_number='')),
                name='vehicle_is_fleet_xor_pov',
            ),
            models.UniqueConstraint(fields=['mission', 'vehicle'], condition=models.Q(vehicle__isnull=False), name='fleet_vehicle_once_per_mission'),
            models.UniqueConstraint(fields=['mission', 'pov_plate_number'], condition=models.Q(is_pov=True), name='pov_plate_once_per_mission'),
            models.UniqueConstraint(fields=['mission', 'sequence'], name='vehicle_sequence_unique_per_mission'),
        ]

    def __str__(self):
        return f'{self.mission_id}: {self.pov_plate_number if self.is_pov else self.vehicle_id}'


class MissionItinerary(models.Model):
    """One leg of a vehicle's plan: origin → (stops) → destination. A vehicle can have several legs."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vehicle_assignment = models.ForeignKey(MissionVehicle, on_delete=models.CASCADE, related_name='itinerary')
    sequence = models.PositiveSmallIntegerField(default=1)
    origin_name = models.CharField(max_length=200)
    origin_location = gis_models.PointField(geography=True, srid=4326)
    origin_mgrs = models.CharField(max_length=32, blank=True)
    destination_name = models.CharField(max_length=200)
    destination_location = gis_models.PointField(geography=True, srid=4326)
    destination_mgrs = models.CharField(max_length=32, blank=True)
    planned_departure = models.DateTimeField(null=True, blank=True)
    planned_arrival = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['sequence']
        constraints = [
            models.UniqueConstraint(fields=['vehicle_assignment', 'sequence'], name='leg_sequence_unique_per_vehicle'),
            models.CheckConstraint(
                check=models.Q(planned_departure__isnull=True) | models.Q(planned_arrival__isnull=True)
                | models.Q(planned_arrival__gte=models.F('planned_departure')),
                name='leg_arrival_not_before_departure',
            ),
        ]


class MissionItineraryStop(models.Model):
    """An intermediate stop on an itinerary leg, in travel order."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    itinerary = models.ForeignKey(MissionItinerary, on_delete=models.CASCADE, related_name='stops')
    sequence = models.PositiveSmallIntegerField(default=1)
    name = models.CharField(max_length=200)
    location = gis_models.PointField(geography=True, srid=4326)
    mgrs = models.CharField(max_length=32, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['sequence']
        constraints = [models.UniqueConstraint(fields=['itinerary', 'sequence'], name='stop_sequence_unique_per_leg')]
