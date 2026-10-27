from django.contrib.gis.geos import Point
from rest_framework import serializers

from .models import HazardAssessment, Mission, MissionApprovalLog


def point_to_repr(point):
    if point is None:
        return None
    return {'lat': point.y, 'lng': point.x}


def repr_to_point(data):
    if not data:
        return None
    return Point(float(data['lng']), float(data['lat']), srid=4326)


class HazardAssessmentSerializer(serializers.ModelSerializer):
    initial_risk_level = serializers.CharField(read_only=True)
    residual_risk_level = serializers.CharField(read_only=True)

    class Meta:
        model = HazardAssessment
        fields = [
            'id', 'mission', 'hazard_description', 'category',
            'probability', 'severity', 'initial_risk_level',
            'existing_controls', 'additional_controls',
            'residual_probability', 'residual_severity', 'residual_risk_level',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'initial_risk_level', 'residual_risk_level', 'created_at', 'updated_at']

    def validate(self, attrs):
        residual_prob = attrs.get('residual_probability', getattr(self.instance, 'residual_probability', ''))
        residual_sev = attrs.get('residual_severity', getattr(self.instance, 'residual_severity', ''))
        if bool(residual_prob) != bool(residual_sev):
            raise serializers.ValidationError(
                'residual_probability and residual_severity must both be set together, or both left blank.'
            )
        return attrs


def mrm_summary(mission):
    """Compact summary of the mission's MRM form (None when it has none)."""
    form = mission.active_mrm
    if form is None:
        return None
    from apps.mrm import risk as mrm_risk
    from apps.mrm.serializers import stage_of

    return {
        'id': str(form.id), 'mrm_number': form.mrm_number, 'stage': stage_of(form),
        'total_percent': form.total_percent, 'risk_category': form.risk_category,
        'authority_level': form.authority_level,
        'authority_level_label': mrm_risk.AUTHORITY_LABELS.get(form.authority_level, ''),
        'authority_name': form.authority_name, 'authority_approved': form.authority_approved,
    }


class MissionApprovalLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source='actor.username', read_only=True, default=None)

    class Meta:
        model = MissionApprovalLog
        fields = ['id', 'mission', 'action', 'actor', 'actor_name', 'comments', 'created_at']
        read_only_fields = ['id', 'created_at']


class MissionListSerializer(serializers.ModelSerializer):
    unit_name = serializers.CharField(source='unit.name', read_only=True, default=None)
    commander_name = serializers.CharField(source='mission_commander.full_name', read_only=True, default=None)
    overall_risk_level = serializers.CharField(read_only=True)
    mrm = serializers.SerializerMethodField()
    category_label = serializers.SerializerMethodField()
    mrm_preparation = serializers.SerializerMethodField()

    def get_mrm(self, obj):
        return mrm_summary(obj)

    def get_category_label(self, obj):
        return obj.get_category_display() if obj.category else 'Uncategorized (legacy)'

    def get_mrm_preparation(self, obj):
        from .ground import MRM_PREP_LABELS, mrm_preparation_status

        status = mrm_preparation_status(obj)
        return {'status': status, 'label': MRM_PREP_LABELS[status]}

    class Meta:
        model = Mission
        fields = [
            'id', 'name', 'status', 'unit', 'unit_name', 'commander_name', 'category', 'category_label',
            'approval_status', 'mrm_preparation',
            'risk_review_status', 'overall_risk_level', 'mrm', 'start_date', 'end_date', 'is_active',
        ]


class MissionDetailSerializer(serializers.ModelSerializer):
    location = serializers.SerializerMethodField()
    location_input = serializers.DictField(write_only=True, required=False, source='location')
    hazard_assessments = HazardAssessmentSerializer(many=True, read_only=True)
    approval_logs = MissionApprovalLogSerializer(many=True, read_only=True)
    overall_risk_level = serializers.CharField(read_only=True)
    overall_residual_risk_level = serializers.CharField(read_only=True)
    submitted_by_name = serializers.CharField(source='submitted_by.username', read_only=True, default=None)
    reviewed_by_name = serializers.CharField(source='reviewed_by.username', read_only=True, default=None)
    mrm = serializers.SerializerMethodField()

    def get_mrm(self, obj):
        return mrm_summary(obj)

    class Meta:
        model = Mission
        fields = [
            'id', 'name', 'description', 'unit', 'mission_commander', 'status', 'mrm',
            'location', 'location_input', 'start_date', 'end_date',
            'risk_review_status', 'submitted_by', 'submitted_by_name', 'submitted_at',
            'reviewed_by', 'reviewed_by_name', 'reviewed_at', 'review_comments',
            'overall_risk_level', 'overall_residual_risk_level',
            'hazard_assessments', 'approval_logs', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'submitted_by', 'submitted_at', 'reviewed_by', 'reviewed_at', 'review_comments',
            'risk_review_status', 'created_at', 'updated_at',
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request is not None:
            from .ground import serialize_planning

            data.update(serialize_planning(instance, request.user))
        return data

    def get_location(self, obj):
        return point_to_repr(obj.location)

    def validate_location_input(self, value):
        return repr_to_point(value)

    def validate(self, attrs):
        start = attrs.get('start_date', getattr(self.instance, 'start_date', None))
        end = attrs.get('end_date', getattr(self.instance, 'end_date', None))
        if start and end and end < start:
            raise serializers.ValidationError('end_date cannot be before start_date.')
        return attrs


class MissionReviewActionSerializer(serializers.Serializer):
    """Body for approve/reject actions."""

    comments = serializers.CharField(required=False, allow_blank=True, default='')
