from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.audit import log_action
from apps.core.models import AuditLog
from apps.core.permissions import ModulePermissionMixin, UnitScopedQuerysetMixin
from apps.core.rbac import Action, Module

from apps.personnel.models import Unit

from . import ground
from .models import HazardAssessment, Mission, MissionApprovalLog, MissionPersonnel
from .serializers import (
    HazardAssessmentSerializer,
    MissionApprovalLogSerializer,
    MissionDetailSerializer,
    MissionListSerializer,
    MissionReviewActionSerializer,
)


def assert_legacy_risk_path_allowed(mission, what='approve'):
    """
    The MRM module owns mission risk assessment and approval. The older hazard-assessment / quick-approval
    path stays available only for missions that have no MRM form AND only while enforcement is off.
    """
    from django.conf import settings

    form = mission.active_mrm
    if form is not None:
        raise ValidationError(
            f'This mission\'s risk assessment is owned by its MRM form {form.mrm_number}. '
            f'Change hazards or {what} it from the MRM module; the legacy hazard list is read-only.'
        )
    if getattr(settings, 'MRM_REQUIRE_FOR_MISSION_APPROVAL', False):
        raise ValidationError('Mission risk assessment and approval require an MRM form. Create one from the MRM module.')


class MissionViewSet(ModulePermissionMixin, UnitScopedQuerysetMixin, viewsets.ModelViewSet):
    """
    Mission profile CRUD, plus the risk-approval workflow:

      DRAFT --submit--> SUBMITTED --approve--> APPROVED
                              \\--reject--> REJECTED --submit--> SUBMITTED (resubmission)
    """

    queryset = Mission.objects.select_related(
        'unit', 'mission_commander', 'submitted_by', 'reviewed_by', 'responsible_section', 'created_by',
        'approval_authority', 'mrm_assignee',
    ).prefetch_related('hazard_assessments', 'approval_logs')
    permission_module = Module.MISSIONS
    action_permission_map = {
        'submit_for_approval': Action.EDIT,
        'approve': Action.APPROVE,
        'reject': Action.APPROVE,
        'hazards': Action.EDIT,
        # category-driven planning workflow
        'submit_mission': Action.EDIT,
        'approve_mission': Action.APPROVE,
        'reject_mission': Action.APPROVE,
        'authorities': Action.VIEW,
        'categories': Action.VIEW,
        'mrm_candidates': Action.VIEW,
        'activity': Action.VIEW,
    }
    filterset_fields = ['status', 'risk_review_status', 'unit', 'is_active', 'category', 'approval_status', 'approval_authority']
    search_fields = ['name', 'description']
    ordering_fields = ['start_date', 'created_at', 'name']

    def get_serializer_class(self):
        if self.action == 'list':
            return MissionListSerializer
        return MissionDetailSerializer

    def get_queryset(self):
        """Unit scoping, plus every mission the user is personally involved in (creator, authority, MRM assignee, crew)."""
        base = super().get_queryset()
        user = self.request.user
        if user.is_superuser or user.role in ('ADMIN', 'COMMANDER'):
            return base
        involvement = (
            Q(created_by=user) | Q(approval_authority=user) | Q(mrm_assignee__linked_account=user)
            | Q(personnel_assignments__personnel__linked_account=user)
        )
        return self.queryset.filter(Q(pk__in=base.values('pk')) | involvement).distinct()

    # --- create / update: category-driven missions go through the planning service ---------------------
    def create(self, request, *args, **kwargs):
        if not request.data.get('category'):
            raise ValidationError({'category': 'Select a mission category (Air Operations or Ground Operations).'})
        mission, created = ground.save_mission(request.user, request.data, None, request)
        data = MissionDetailSerializer(mission, context=self.get_serializer_context()).data
        return Response(data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        partial = kwargs.get('partial', False)
        if instance.category and (ground.PLANNING_KEYS & set(request.data.keys())):
            payload = {**ground.payload_from_instance(instance), **request.data} if partial else dict(request.data)
            mission, _ = ground.save_mission(request.user, payload, instance, request)
            return Response(MissionDetailSerializer(mission, context=self.get_serializer_context()).data)
        if instance.category and request.data.get('status') == Mission.Status.APPROVED and instance.approval_status != Mission.ApprovalStatus.APPROVED:
            raise ValidationError({'status': 'A mission becomes Approved only when its approving authority approves it.'})
        return super().update(request, *args, **kwargs)

    # --- planning workflow actions -----------------------------------------------------------------
    @action(detail=False, methods=['get'])
    def categories(self, request):
        return Response({
            'categories': ground.category_catalog(),
            'roles': [{'value': r.value, 'label': r.label} for r in MissionPersonnel.Role],
        })

    @action(detail=False, methods=['get'])
    def authorities(self, request):
        unit = Unit.objects.filter(pk=request.query_params.get('unit'), is_active=True).first() if request.query_params.get('unit') else None
        if unit is None:
            raise ValidationError({'unit': 'Choose the Unit Primary Responsible first.'})
        if not ground._in_scope(request.user, unit.pk):
            raise PermissionDenied('That unit is outside your scope.')
        return Response([
            {'id': str(u.pk), 'name': u.display_name_with_rank, 'designation': u.get_mrm_designation_display() or u.get_role_display(),
             'unit': u.unit.code if u.unit_id else None}
            for u in ground.mission_authority_candidates(unit, exclude_user=request.user)
        ])

    @action(detail=True, methods=['get'], url_path='mrm-candidates')
    def mrm_candidates(self, request, pk=None):
        return Response([ground._person_brief(p) for p in ground.mrm_assignee_candidates(self.get_object())])

    @action(detail=True, methods=['get'])
    def activity(self, request, pk=None):
        return Response(ground.mission_activity(self.get_object()))

    @action(detail=True, methods=['post'], url_path='submit-mission')
    def submit_mission(self, request, pk=None):
        mission, newly = ground.submit_mission(request.user, self.get_object(), request)
        data = MissionDetailSerializer(mission, context=self.get_serializer_context()).data
        data['newly_submitted'] = newly
        return Response(data)

    @action(detail=True, methods=['post'], url_path='approve-mission')
    def approve_mission(self, request, pk=None):
        mission = ground.decide_mission(request.user, self.get_object(), True, request.data.get('comments', ''), request)
        return Response(MissionDetailSerializer(mission, context=self.get_serializer_context()).data)

    @action(detail=True, methods=['post'], url_path='reject-mission')
    def reject_mission(self, request, pk=None):
        mission = ground.decide_mission(request.user, self.get_object(), False, request.data.get('comments', ''), request)
        return Response(MissionDetailSerializer(mission, context=self.get_serializer_context()).data)

    def perform_create(self, serializer):
        instance = serializer.save()
        log_action(
            user=self.request.user, action=AuditLog.Action.CREATE, instance=instance,
            description=f'Created mission profile "{instance.name}"', request=self.request,
        )

    def perform_update(self, serializer):
        instance = serializer.save()
        log_action(
            user=self.request.user, action=AuditLog.Action.UPDATE, instance=instance,
            description=f'Updated mission profile "{instance.name}"', request=self.request,
        )

    def perform_destroy(self, instance):
        log_action(
            user=self.request.user, action=AuditLog.Action.DELETE, instance=instance,
            description=f'Deactivated mission "{instance.name}"', request=self.request,
        )
        instance.is_active = False
        instance.save(update_fields=['is_active'])

    @staticmethod
    def _require_no_mrm(mission):
        assert_legacy_risk_path_allowed(mission, what='approve')

    @action(detail=True, methods=['post'], url_path='submit-for-approval')
    def submit_for_approval(self, request, pk=None):
        mission = self.get_object()
        self._require_no_mrm(mission)
        if mission.risk_review_status not in (Mission.RiskReviewStatus.DRAFT, Mission.RiskReviewStatus.REJECTED):
            raise ValidationError(f'Cannot submit a mission in "{mission.risk_review_status}" status.')
        if not mission.hazard_assessments.filter(is_active=True).exists():
            raise ValidationError('At least one hazard assessment is required before submitting for approval.')

        mission.risk_review_status = Mission.RiskReviewStatus.SUBMITTED
        mission.submitted_by = request.user
        mission.submitted_at = timezone.now()
        mission.save(update_fields=['risk_review_status', 'submitted_by', 'submitted_at'])

        MissionApprovalLog.objects.create(
            mission=mission, action=MissionApprovalLog.Action.SUBMITTED, actor=request.user,
        )
        log_action(
            user=request.user, action=AuditLog.Action.OTHER, instance=mission,
            description=f'Submitted mission "{mission.name}" for risk approval', request=request,
        )
        return Response(MissionDetailSerializer(mission).data)

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        # HasModulePermission (via action_permission_map above) already
        # requires Action.APPROVE for this endpoint — only roles granted
        # APPROVE on the MISSIONS module (COMMANDER/ADMIN by default) reach here.
        mission = self.get_object()
        self._require_no_mrm(mission)
        if mission.risk_review_status != Mission.RiskReviewStatus.SUBMITTED:
            raise ValidationError('Mission is not pending approval.')

        serializer = MissionReviewActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        mission.risk_review_status = Mission.RiskReviewStatus.APPROVED
        mission.status = Mission.Status.APPROVED
        mission.reviewed_by = request.user
        mission.reviewed_at = timezone.now()
        mission.review_comments = serializer.validated_data['comments']
        mission.save(update_fields=['risk_review_status', 'status', 'reviewed_by', 'reviewed_at', 'review_comments'])

        MissionApprovalLog.objects.create(
            mission=mission, action=MissionApprovalLog.Action.APPROVED, actor=request.user,
            comments=serializer.validated_data['comments'],
        )
        log_action(
            user=request.user, action=AuditLog.Action.APPROVE, instance=mission,
            description=f'Approved risk assessment for mission "{mission.name}"', request=request,
        )
        return Response(MissionDetailSerializer(mission).data)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        mission = self.get_object()
        self._require_no_mrm(mission)
        if mission.risk_review_status != Mission.RiskReviewStatus.SUBMITTED:
            raise ValidationError('Mission is not pending approval.')

        serializer = MissionReviewActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data['comments']:
            raise ValidationError('A comment explaining the rejection is required.')

        mission.risk_review_status = Mission.RiskReviewStatus.REJECTED
        mission.reviewed_by = request.user
        mission.reviewed_at = timezone.now()
        mission.review_comments = serializer.validated_data['comments']
        mission.save(update_fields=['risk_review_status', 'reviewed_by', 'reviewed_at', 'review_comments'])

        MissionApprovalLog.objects.create(
            mission=mission, action=MissionApprovalLog.Action.REJECTED, actor=request.user,
            comments=serializer.validated_data['comments'],
        )
        log_action(
            user=request.user, action=AuditLog.Action.REJECT, instance=mission,
            description=f'Rejected risk assessment for mission "{mission.name}"', request=request,
        )
        return Response(MissionDetailSerializer(mission).data)

    @action(detail=True, methods=['get', 'post'], url_path='hazards')
    def hazards(self, request, pk=None):
        mission = self.get_object()
        if request.method == 'GET':
            return Response(
                HazardAssessmentSerializer(mission.hazard_assessments.filter(is_active=True), many=True).data
            )

        assert_legacy_risk_path_allowed(mission, what='edit')
        serializer = HazardAssessmentSerializer(data={**request.data, 'mission': mission.id})
        serializer.is_valid(raise_exception=True)
        hazard = serializer.save()
        log_action(
            user=request.user, action=AuditLog.Action.CREATE, instance=hazard,
            description=f'Added hazard assessment to mission "{mission.name}" '
                        f'(initial risk: {hazard.initial_risk_level})',
            request=request,
        )
        return Response(HazardAssessmentSerializer(hazard).data, status=201)


class HazardAssessmentViewSet(ModulePermissionMixin, viewsets.ModelViewSet):
    """Direct CRUD for hazard assessments (in addition to the nested /missions/{id}/hazards/ action)."""

    queryset = HazardAssessment.objects.select_related('mission').all()
    serializer_class = HazardAssessmentSerializer
    permission_module = Module.MISSIONS
    filterset_fields = ['mission', 'category', 'initial_risk_level', 'is_active']
    ordering_fields = ['created_at']

    def perform_create(self, serializer):
        assert_legacy_risk_path_allowed(serializer.validated_data['mission'], what='edit')
        instance = serializer.save()
        log_action(
            user=self.request.user, action=AuditLog.Action.CREATE, instance=instance,
            description=f'Added hazard assessment to mission "{instance.mission.name}"', request=self.request,
        )

    def perform_update(self, serializer):
        assert_legacy_risk_path_allowed(serializer.instance.mission, what='edit')
        instance = serializer.save()
        log_action(
            user=self.request.user, action=AuditLog.Action.UPDATE, instance=instance,
            description=f'Updated hazard assessment for mission "{instance.mission.name}"', request=self.request,
        )

    def perform_destroy(self, instance):
        assert_legacy_risk_path_allowed(instance.mission, what='edit')
        log_action(
            user=self.request.user, action=AuditLog.Action.DELETE, instance=instance,
            description=f'Removed hazard assessment from mission "{instance.mission.name}"', request=self.request,
        )
        instance.is_active = False
        instance.save(update_fields=['is_active'])


class MissionApprovalLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only history of mission approval-workflow transitions."""

    queryset = MissionApprovalLog.objects.select_related('mission', 'actor').all()
    serializer_class = MissionApprovalLogSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['mission', 'action']
