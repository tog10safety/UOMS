from rest_framework import serializers

from apps.accounts.models import User

from . import access, risk
from .models import (
    Hazard, MRMEvent, MRMFeedback, MRMForm, MRMPersonnel, SafetyOfficerAssignment, UnitLogo,
)


def _level_block(likelihood, severity):
    rating = risk.rating(likelihood, severity)
    return {'likelihood': likelihood, 'severity': severity, 'rating': rating, 'level': risk.level(rating)}


def _user_brief(user):
    if user is None:
        return None
    return {
        'id': str(user.id), 'username': user.username, 'full_name': user.full_name,
        'display_name': user.display_name_with_rank, 'unit': user.unit.code if user.unit_id else None,
        'mrm_authority': user.effective_mrm_authority, 'mrm_designation': user.mrm_designation,
    }


# ---------------------------------------------------------------------------
# Hazard registry
# ---------------------------------------------------------------------------

class HazardSerializer(serializers.ModelSerializer):
    unit_name = serializers.CharField(source='unit.name', read_only=True)
    unit_code = serializers.CharField(source='unit.code', read_only=True)
    created_by_name = serializers.CharField(source='created_by.full_name', read_only=True, default=None)
    before_level = serializers.CharField(read_only=True)
    after_level = serializers.CharField(read_only=True)
    in_use = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()

    class Meta:
        model = Hazard
        fields = [
            'id', 'unit', 'unit_name', 'unit_code', 'activity_code', 'hazard_description',
            'before_likelihood', 'before_severity', 'before_risk_rating', 'before_level',
            'mitigations',
            'after_likelihood', 'after_severity', 'after_risk_rating', 'after_level',
            'created_by_name', 'in_use', 'can_edit', 'created_at', 'updated_at',
        ]
        # `unit` is chosen once at creation (the view resolves and authorises it) and is never editable afterwards,
        # otherwise an evaluator could move a hazard into a unit they do not belong to.
        read_only_fields = ['id', 'unit', 'before_risk_rating', 'after_risk_rating', 'created_at', 'updated_at']

    def get_in_use(self, obj):
        return obj.mrm_links.exists()

    def get_can_edit(self, obj):
        request = self.context.get('request')
        return bool(request and access.can_write_hazard(request.user, obj))

    def validate(self, attrs):
        for prefix in ('before', 'after'):
            likelihood = attrs.get(f'{prefix}_likelihood', getattr(self.instance, f'{prefix}_likelihood', None))
            severity = attrs.get(f'{prefix}_severity', getattr(self.instance, f'{prefix}_severity', None))
            try:
                attrs[f'{prefix}_likelihood'], attrs[f'{prefix}_severity'] = risk.normalize(likelihood, severity)
            except risk.RiskInputError as exc:
                raise serializers.ValidationError({f'{prefix}_likelihood': str(exc)})
        for field in ('activity_code', 'hazard_description', 'mitigations'):
            if field in attrs and not str(attrs[field]).strip():
                raise serializers.ValidationError({field: 'This field is required.'})
            if field in attrs:
                attrs[field] = str(attrs[field]).strip()
        return attrs


# ---------------------------------------------------------------------------
# MRM forms
# ---------------------------------------------------------------------------

def _roles(form, user):
    roles = []
    if form.created_by_id == user.id:
        roles.append('creator')
    if form.reviewed_by_id == user.id:
        roles.append('reviewer')
    if form.authority_assigned_to_id == user.id:
        roles.append('authority')
    if form.tagged_personnel.filter(user=user, is_active=True).exists():
        roles.append('tagged')
    return roles


def serialize_form_list_item(form, user):
    return {
        'id': str(form.id), 'mrm_number': form.mrm_number, 'activity_mission': form.activity_mission,
        'mission': str(form.mission_id) if form.mission_id else None,
        'mission_name': form.mission.name if form.mission_id else None,
        'unit': str(form.unit_id) if form.unit_id else None,
        'unit_name': form.unit.name if form.unit_id else None,
        'unit_code': form.unit.code if form.unit_id else None,
        'creator_name': form.creator_name, 'reviewer_name': form.reviewer_name, 'authority_name': form.authority_name,
        'status': form.status, 'review_status': form.review_status,
        'total_percent': form.total_percent, 'risk_category': form.risk_category,
        'authority_level': form.authority_level,
        'authority_level_label': risk.AUTHORITY_LABELS.get(form.authority_level, ''),
        'authority_approved': form.authority_approved,
        'stage': stage_of(form),
        'has_pdf': bool(form.approved_pdf),
        'my_roles': _roles(form, user),
        'created_at': form.created_at, 'date_submitted': form.date_submitted,
        'authority_approval_date': form.authority_approval_date,
    }


def stage_of(form):
    """A single human-friendly workflow stage for list badges."""
    if form.authority_approved:
        return 'approved'
    if form.status == MRMForm.Status.DRAFT:
        return 'draft'
    if form.status == MRMForm.Status.SUBMITTED:
        return 'awaiting_review'
    if form.review_status == MRMForm.ReviewStatus.APPROVED:
        return 'awaiting_authority' if form.authority_assigned_to_id else 'needs_authority_assignment'
    return form.review_status  # rejected | needs_revision


def serialize_hazard_line(mh):
    snap = mh.snapshot or {}
    h = mh.hazard
    before_l = snap.get('before_likelihood', h.before_likelihood)
    before_s = snap.get('before_severity', h.before_severity)
    after_l = snap.get('after_likelihood', h.after_likelihood)
    after_s = snap.get('after_severity', h.after_severity)
    residual_l, residual_s = mh.effective_residual
    return {
        'id': mh.id, 'hazard': str(h.id),
        'activity_code': snap.get('activity_code', h.activity_code),
        'hazard_description': snap.get('hazard_description', h.hazard_description),
        'mitigations': snap.get('mitigations', h.mitigations),
        'before': _level_block(before_l, before_s),
        'registry_after': _level_block(after_l, after_s),
        'override': _level_block(mh.override_likelihood, mh.override_severity) if mh.has_override else None,
        'additional_mitigations': mh.additional_mitigations,
        'residual': _level_block(residual_l, residual_s),
        'registry_changed': bool(snap) and (
            snap.get('after_risk_rating') != h.after_risk_rating or snap.get('mitigations') != h.mitigations
        ),
    }


def serialize_capabilities(form, user):
    mode, message = access.edit_mode(form, user)
    return {
        'edit': mode, 'edit_message': message,
        'delete': access.can_delete_form(form, user),
        'submit': access.can_submit(form, user),
        'review': access.can_review(form, user),
        'authority_approve': access.can_authority_approve(form, user),
        'reassign_authority': access.can_reassign_authority(form, user),
        'reassign_reviewer': access.can_reassign_reviewer(form, user),
        'manage_personnel': access.can_manage_personnel(form, user),
        'sign': access.can_sign(form, user),
        'give_feedback': access.can_give_feedback(form, user),
        'regenerate_pdf': access.is_admin(user) or (access.is_uso(user) and form.unit_id in (access.scope_unit_ids(user) or set())),
        'is_resubmission': form.status == MRMForm.Status.REVIEWED and form.review_status in (
            MRMForm.ReviewStatus.REJECTED, MRMForm.ReviewStatus.NEEDS_REVISION),
    }


def serialize_form_detail(form, user):
    data = serialize_form_list_item(form, user)
    tagged = form.tagged_personnel.filter(is_active=True).select_related('user')
    feedback_done = set(form.feedback_items.values_list('user_id', flat=True))
    data.update({
        'safety_objectives': form.safety_objectives, 'imsafe': form.imsafe,
        'aircraft_vehicle': form.aircraft_vehicle, 'mission_statement': form.mission_statement,
        'environment': form.environment, 'environment_data': form.environment_data,
        'hazards': [serialize_hazard_line(mh) for mh in form.mission_hazards.select_related('hazard')],
        'risk': {
            'max_risk': form.max_risk, 'residual_risk': form.residual_risk, 'total_percent': form.total_percent,
            'risk_category': form.risk_category, 'authority_level': form.authority_level,
            'authority_level_label': risk.AUTHORITY_LABELS.get(form.authority_level, ''),
            'authority_range': risk.AUTHORITY_RANGE_LABELS.get(form.authority_level, ''),
        },
        'creator': _user_brief(form.created_by), 'reviewer': _user_brief(form.reviewed_by),
        'authority': _user_brief(form.authority_assigned_to),
        'review_notes': form.review_notes, 'date_reviewed': form.date_reviewed,
        'creator_signed': form.creator_signed, 'creator_signature_date': form.creator_signature_date,
        'evaluator_signed': form.evaluator_signed, 'evaluator_signature_date': form.evaluator_signature_date,
        'completion_time_seconds': form.completion_time_seconds,
        'feedback_collection_closed': form.feedback_collection_closed,
        'tagged_personnel': [
            {'id': str(t.id), 'user': str(t.user_id), 'name': t.user.display_name_with_rank, 'role': t.role,
             'feedback_submitted': t.user_id in feedback_done}
            for t in tagged
        ],
        'feedback_counts': {
            'submitted': form.feedback_items.count(),
            'pending_review': form.feedback_items.filter(status=MRMFeedback.Status.PENDING).count(),
            'awaiting': max(tagged.count() - len([t for t in tagged if t.user_id in feedback_done]), 0),
        },
        'events': [
            {'id': e.id, 'kind': e.kind, 'label': e.get_kind_display(), 'actor': e.actor_name,
             'comments': e.comments, 'metadata': e.metadata, 'created_at': e.created_at}
            for e in form.events.all()
        ],
        'can': serialize_capabilities(form, user),
    })
    return data


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

def serialize_feedback(fb, viewer):
    hide = fb.is_anonymous and fb.user_id != viewer.id and not access.is_admin(viewer)
    return {
        'id': str(fb.id), 'mrm': str(fb.mrm_id), 'mrm_number': fb.mrm.mrm_number,
        'activity_mission': fb.mrm.activity_mission, 'unit_name': fb.mrm.unit.name if fb.mrm.unit_id else None,
        'submitted_by': None if hide else fb.user.display_name_with_rank, 'is_anonymous': fb.is_anonymous,
        'risk_assessment_accuracy': fb.risk_assessment_accuracy,
        'hazard_identification_rating': fb.hazard_identification_rating,
        'mitigation_effectiveness': fb.mitigation_effectiveness,
        'what_went_well': fb.what_went_well, 'what_could_be_improved': fb.what_could_be_improved,
        'new_hazards_identified': fb.new_hazards_identified, 'lessons_learned': fb.lessons_learned,
        'additional_comments': fb.additional_comments,
        'recommend_add_to_hazard_registry': fb.recommend_add_to_hazard_registry,
        'recommended_hazard_description': fb.recommended_hazard_description,
        'recommended_mitigations': fb.recommended_mitigations,
        'status': fb.status, 'submitted_at': fb.submitted_at,
        'reviewed_by': fb.reviewed_by.full_name if fb.reviewed_by_id else None, 'reviewed_at': fb.reviewed_at,
        'review_notes': fb.review_notes, 'action_taken': fb.action_taken, 'action_taken_at': fb.action_taken_at,
        'can_review': access.can_review_feedback(fb, viewer),
    }


# ---------------------------------------------------------------------------
# Safety-officer admin
# ---------------------------------------------------------------------------

class SafetyAssignmentSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    unit_name = serializers.CharField(source='unit.name', read_only=True)
    unit_code = serializers.CharField(source='unit.code', read_only=True)

    class Meta:
        model = SafetyOfficerAssignment
        fields = ['id', 'user', 'username', 'user_name', 'unit', 'unit_name', 'unit_code', 'is_primary', 'is_active']

    def validate_user(self, user):
        if user.effective_mrm_authority != User.MRMAuthority.UNIT_SAFETY_OFFICER:
            raise serializers.ValidationError('Only Unit Safety Officers can be given unit assignments.')
        return user


class UnitLogoSerializer(serializers.ModelSerializer):
    unit_name = serializers.CharField(source='unit.name', read_only=True)
    unit_code = serializers.CharField(source='unit.code', read_only=True)

    class Meta:
        model = UnitLogo
        fields = ['id', 'unit', 'unit_name', 'unit_code', 'image', 'created_at']
        read_only_fields = ['id', 'created_at']
