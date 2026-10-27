"""
Mission Risk Management (MRM) — Django port of the legacy Flask MRM system.

Design notes
------------
* Users, units and the unit hierarchy are NOT duplicated: they are UOMS's
  ``accounts.User`` and ``personnel.Unit``. The MRM-specific attributes
  (authority, designation, signature) live on ``accounts.User``.
* An ``MRMForm`` can be linked to a UOMS ``Mission``; the form is then the
  source of truth for that mission's risk-approval status (see services.sync_mission).
* Hazards chosen for a form are *snapshotted* on ``MissionHazard`` so that later
  edits to the hazard registry can never silently change an approved safety record.
* The legacy ``edit_history`` JSON blob and UserActivity table are replaced by
  ``MRMEvent`` (per-form timeline) and the existing UOMS ``AuditLog``.
"""
from django.conf import settings
from django.db import models

from apps.core.models import BaseModel
from apps.personnel.models import Unit

from . import risk


def _user_fk(related_name, **kwargs):
    return models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name=related_name, **kwargs,
    )


class UnitLogo(BaseModel):
    """Logo printed on a unit's MRM PDFs."""

    unit = models.OneToOneField(Unit, on_delete=models.CASCADE, related_name='mrm_logo')
    image = models.ImageField(upload_to='mrm/unit_logos/')
    uploaded_by = _user_fk('+')

    def __str__(self):
        return f'Logo — {self.unit.code}'


class SafetyOfficerAssignment(BaseModel):
    """A Unit Safety Officer's area of responsibility (one officer may cover several units)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='safety_assignments')
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='safety_officer_assignments')
    is_primary = models.BooleanField(default=False)

    class Meta(BaseModel.Meta):
        constraints = [models.UniqueConstraint(fields=['user', 'unit'], name='unique_safety_assignment')]

    def __str__(self):
        return f'{self.user.username} → {self.unit.code}'


class Hazard(BaseModel):
    """Reusable hazard in a unit's hazard registry (likelihood 1-5 x severity A-E)."""

    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name='mrm_hazards')
    activity_code = models.CharField(max_length=100)
    hazard_description = models.TextField()

    before_likelihood = models.PositiveSmallIntegerField()
    before_severity = models.CharField(max_length=1)
    before_risk_rating = models.CharField(max_length=2, editable=False)

    mitigations = models.TextField()

    after_likelihood = models.PositiveSmallIntegerField()
    after_severity = models.CharField(max_length=1)
    after_risk_rating = models.CharField(max_length=2, editable=False)

    created_by = _user_fk('mrm_hazards_created')
    legacy_id = models.IntegerField(null=True, blank=True, unique=True, editable=False)

    class Meta(BaseModel.Meta):
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['unit', 'activity_code']),
            models.Index(fields=['after_risk_rating']),
        ]

    def __str__(self):
        return f'{self.activity_code}: {self.hazard_description[:60]}'

    @property
    def before_level(self):
        return risk.level(self.before_risk_rating)

    @property
    def after_level(self):
        return risk.level(self.after_risk_rating)

    def save(self, *args, **kwargs):
        self.before_likelihood, self.before_severity = risk.normalize(self.before_likelihood, self.before_severity)
        self.after_likelihood, self.after_severity = risk.normalize(self.after_likelihood, self.after_severity)
        self.before_risk_rating = risk.rating(self.before_likelihood, self.before_severity)
        self.after_risk_rating = risk.rating(self.after_likelihood, self.after_severity)
        super().save(*args, **kwargs)


class MRMForm(BaseModel):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        SUBMITTED = 'submitted', 'Submitted'
        REVIEWED = 'reviewed', 'Reviewed'

    class ReviewStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        NEEDS_REVISION = 'needs_revision', 'Needs Revision'

    mrm_number = models.CharField(max_length=20, unique=True)
    mission = models.ForeignKey(
        'missions.Mission', null=True, blank=True, on_delete=models.SET_NULL, related_name='mrm_forms',
        help_text='Optional UOMS mission this assessment belongs to.',
    )
    activity_mission = models.CharField(max_length=255)

    # --- ownership & routing ---------------------------------------------
    unit = models.ForeignKey(Unit, null=True, on_delete=models.PROTECT, related_name='mrm_forms',
                             help_text="The creator's unit at creation time — drives visibility.")
    creator_unit = models.ForeignKey(Unit, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    reviewer_unit = models.ForeignKey(Unit, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    authority_unit = models.ForeignKey(Unit, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_by = _user_fk('mrm_created')
    reviewed_by = _user_fk('mrm_reviews')
    authority_assigned_to = _user_fk('mrm_authority_assignments')
    last_edited_by = _user_fk('+')
    # Display-name snapshots so printed/approved records survive later renames.
    creator_name = models.CharField(max_length=350, blank=True)
    reviewer_name = models.CharField(max_length=350, blank=True)
    authority_name = models.CharField(max_length=350, blank=True)

    # --- content ----------------------------------------------------------
    safety_objectives = models.TextField()
    imsafe = models.JSONField(default=dict, blank=True, help_text="I'M SAFE checklist, e.g. {'I': true, ...}")
    aircraft_vehicle = models.CharField(max_length=255, blank=True)
    environment_data = models.JSONField(default=dict, blank=True)
    environment = models.TextField(blank=True, help_text='Rendered sentence derived from environment_data.')
    mission_statement = models.TextField(blank=True)

    # --- computed risk ------------------------------------------------------
    max_risk = models.PositiveIntegerField(default=0)
    residual_risk = models.PositiveIntegerField(default=0)
    total_percent = models.FloatField(default=0)
    authority_level = models.CharField(
        max_length=30, blank=True,
        choices=[(code, risk.AUTHORITY_LABELS[code]) for _, code in risk.AUTHORITY_TIERS],
    )
    risk_category = models.CharField(max_length=20, blank=True)

    # --- workflow -----------------------------------------------------------
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    date_submitted = models.DateTimeField(null=True, blank=True)
    review_status = models.CharField(max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.PENDING)
    date_reviewed = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)

    creator_signed = models.BooleanField(default=False)
    creator_signature_date = models.DateTimeField(null=True, blank=True)
    evaluator_signed = models.BooleanField(default=False)
    evaluator_signature_date = models.DateTimeField(null=True, blank=True)
    authority_approved = models.BooleanField(default=False)
    authority_approval_date = models.DateTimeField(null=True, blank=True)

    approved_pdf = models.FileField(upload_to='mrm/approved_pdfs/', null=True, blank=True)
    completion_time_seconds = models.PositiveIntegerField(null=True, blank=True)
    last_edited = models.DateTimeField(null=True, blank=True)

    # --- post-mission feedback ---------------------------------------------
    feedback_deadline = models.DateTimeField(null=True, blank=True)
    feedback_collection_closed = models.BooleanField(default=False)
    debrief_date = models.DateTimeField(null=True, blank=True)
    lessons_learned_summary = models.TextField(blank=True)

    legacy_id = models.IntegerField(null=True, blank=True, unique=True, editable=False)

    class Meta(BaseModel.Meta):
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_by', 'status']),
            models.Index(fields=['reviewed_by', 'review_status']),
            models.Index(fields=['authority_assigned_to', 'authority_approved']),
            models.Index(fields=['status', 'authority_level']),
            models.Index(fields=['unit', 'risk_category']),
            models.Index(fields=['feedback_deadline', 'feedback_collection_closed']),
        ]

    def __str__(self):
        return f'MRM {self.mrm_number} — {self.activity_mission}'

    @property
    def risk_summary(self):
        return risk.RiskSummary(
            self.max_risk, self.residual_risk, self.total_percent, self.authority_level or 'OPERATOR',
            self.risk_category or 'Low',
        )

    @property
    def is_locked(self):
        """Once the decision authority has signed, the record is immutable."""
        return self.authority_approved


class MissionHazard(models.Model):
    """A registry hazard selected for an MRM, with optional residual-risk override and a frozen snapshot."""

    id = models.BigAutoField(primary_key=True)
    mrm = models.ForeignKey(MRMForm, on_delete=models.CASCADE, related_name='mission_hazards')
    hazard = models.ForeignKey(Hazard, on_delete=models.PROTECT, related_name='mrm_links')
    override_likelihood = models.PositiveSmallIntegerField(null=True, blank=True)
    override_severity = models.CharField(max_length=1, blank=True)
    additional_mitigations = models.TextField(blank=True)
    snapshot = models.JSONField(default=dict, blank=True, help_text='Registry values as they were when selected.')
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['position', 'id']
        constraints = [models.UniqueConstraint(fields=['mrm', 'hazard'], name='unique_hazard_per_mrm')]

    def __str__(self):
        return f'{self.mrm.mrm_number} · {self.hazard_id}'

    def take_snapshot(self):
        h = self.hazard
        self.snapshot = {
            'activity_code': h.activity_code,
            'hazard_description': h.hazard_description,
            'before_likelihood': h.before_likelihood,
            'before_severity': h.before_severity,
            'before_risk_rating': h.before_risk_rating,
            'mitigations': h.mitigations,
            'after_likelihood': h.after_likelihood,
            'after_severity': h.after_severity,
            'after_risk_rating': h.after_risk_rating,
        }

    @property
    def has_override(self):
        return self.override_likelihood is not None and bool(self.override_severity)

    @property
    def effective_residual(self):
        """(likelihood, severity) used for risk maths: the override when set, else the snapshot's after-value."""
        if self.has_override:
            return int(self.override_likelihood), self.override_severity
        snap = self.snapshot or {}
        return (
            int(snap.get('after_likelihood', self.hazard.after_likelihood)),
            snap.get('after_severity', self.hazard.after_severity),
        )

    @property
    def effective_residual_rating(self):
        return risk.rating(*self.effective_residual)


class MRMPersonnel(BaseModel):
    """A user tagged on a mission — they are asked for post-mission feedback."""

    mrm = models.ForeignKey(MRMForm, on_delete=models.CASCADE, related_name='tagged_personnel')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tagged_mrms')
    role = models.CharField(max_length=100, default='Crew Member')
    tagged_by = _user_fk('+')

    class Meta(BaseModel.Meta):
        constraints = [models.UniqueConstraint(fields=['mrm', 'user'], name='unique_tag_per_mrm')]

    def __str__(self):
        return f'{self.user.username} on {self.mrm.mrm_number}'


class MRMFeedback(BaseModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        REVIEWED = 'reviewed', 'Reviewed'
        ACTION_TAKEN = 'action_taken', 'Action Taken'

    mrm = models.ForeignKey(MRMForm, on_delete=models.CASCADE, related_name='feedback_items')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='mrm_feedback')

    risk_assessment_accuracy = models.PositiveSmallIntegerField(default=3)
    hazard_identification_rating = models.PositiveSmallIntegerField(default=3)
    mitigation_effectiveness = models.PositiveSmallIntegerField(default=3)

    what_went_well = models.TextField(blank=True)
    what_could_be_improved = models.TextField(blank=True)
    new_hazards_identified = models.TextField(blank=True)
    lessons_learned = models.TextField(blank=True)
    additional_comments = models.TextField(blank=True)

    recommend_add_to_hazard_registry = models.BooleanField(default=False)
    recommended_hazard_description = models.TextField(blank=True)
    recommended_mitigations = models.TextField(blank=True)

    is_anonymous = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(auto_now_add=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reviewed_by = _user_fk('mrm_feedback_reviews')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    action_taken = models.TextField(blank=True)
    action_taken_by = _user_fk('+')
    action_taken_at = models.DateTimeField(null=True, blank=True)

    legacy_id = models.IntegerField(null=True, blank=True, unique=True, editable=False)

    class Meta(BaseModel.Meta):
        ordering = ['-submitted_at']
        constraints = [models.UniqueConstraint(fields=['mrm', 'user'], name='one_feedback_per_user_per_mrm')]
        indexes = [models.Index(fields=['mrm', 'status']), models.Index(fields=['status'])]

    def __str__(self):
        return f'Feedback {self.mrm.mrm_number} by {self.user.username}'


class FeedbackNotification(BaseModel):
    """Unread-feedback marker for Unit Safety Officers."""

    feedback = models.ForeignKey(MRMFeedback, on_delete=models.CASCADE, related_name='notifications')
    officer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='feedback_notifications')
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=['officer', 'is_read'])]


class MRMEvent(models.Model):
    """Append-only timeline of everything that happens to an MRM form."""

    class Kind(models.TextChoices):
        CREATED = 'CREATED', 'Created'
        EDITED = 'EDITED', 'Edited'
        SUBMITTED = 'SUBMITTED', 'Submitted for review'
        REVIEW_APPROVED = 'REVIEW_APPROVED', 'Evaluator approved'
        REVIEW_REJECTED = 'REVIEW_REJECTED', 'Evaluator rejected'
        REVIEW_REVISION = 'REVIEW_REVISION', 'Evaluator requested revision'
        AUTHORITY_ASSIGNED = 'AUTHORITY_ASSIGNED', 'Decision authority assigned'
        AUTHORITY_APPROVED = 'AUTHORITY_APPROVED', 'Decision authority approved'
        SIGNED = 'SIGNED', 'Signed'
        PERSONNEL = 'PERSONNEL', 'Personnel tagged/untagged'
        FEEDBACK_CLOSED = 'FEEDBACK_CLOSED', 'Feedback collection closed'
        ARCHIVED = 'ARCHIVED', 'Archived'
        PDF = 'PDF', 'PDF regenerated'

    id = models.BigAutoField(primary_key=True)
    mrm = models.ForeignKey(MRMForm, on_delete=models.CASCADE, related_name='events')
    kind = models.CharField(max_length=30, choices=Kind.choices)
    actor = _user_fk('+')
    actor_name = models.CharField(max_length=350, blank=True)
    comments = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
        indexes = [models.Index(fields=['mrm', 'created_at'])]

    def __str__(self):
        return f'{self.mrm.mrm_number}: {self.kind}'
