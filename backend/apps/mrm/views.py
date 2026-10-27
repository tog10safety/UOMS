import io
from collections import Counter

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Avg, Count, Q
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from PIL import Image as PILImage
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.core.audit import log_action
from apps.core.models import AuditLog
from apps.core.permissions import has_module_permission
from apps.core.rbac import Action, Module
from apps.personnel.models import Unit

from . import access, constants, importers, risk, services
from .models import (
    FeedbackNotification, Hazard, MRMFeedback, MRMForm, MRMPersonnel, SafetyOfficerAssignment, UnitLogo,
)
from .serializers import (
    HazardSerializer, SafetyAssignmentSerializer, UnitLogoSerializer, serialize_feedback,
    serialize_form_detail, serialize_form_list_item,
)

XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
MAX_IMAGE_BYTES = 2 * 1024 * 1024


class BadInputAs400:
    """Malformed ids (e.g. ?unit=abc for a UUID column) raise Django ValidationError; answer 400 instead of 500."""

    def handle_exception(self, exc):
        if isinstance(exc, DjangoValidationError):
            exc = ValidationError({'detail': exc.messages})
        return super().handle_exception(exc)


class MRMAccess(BasePermission):
    """
    Base gate for every MRM endpoint: the UOMS role must be allowed to view the Mission Risk Management
    module (RolePermission matrix). What a user can then *do* is decided by their MRM authority
    (apps.mrm.access), exactly as in the legacy system.
    """

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated
            and has_module_permission(request.user, Module.MISSIONS, Action.VIEW)
        )


def validate_image_upload(upload):
    if upload is None:
        raise ValidationError({'detail': 'No file was uploaded.'})
    if upload.size > MAX_IMAGE_BYTES:
        raise ValidationError({'detail': 'Image must be 2 MB or smaller.'})
    try:
        image = PILImage.open(upload)
        image_format = image.format
        image.verify()
    except Exception:
        raise ValidationError({'detail': 'The file is not a valid image.'})
    if image_format not in ('PNG', 'JPEG'):
        raise ValidationError({'detail': 'Only PNG or JPEG images are allowed.'})
    upload.seek(0)
    return upload


# ---------------------------------------------------------------------------
# Config / me / signature / work queue
# ---------------------------------------------------------------------------

class ConfigView(BadInputAs400, APIView):
    permission_classes = [MRMAccess]

    def get(self, request):
        return Response({
            'activity_codes': constants.ACTIVITY_CODES,
            'environment_options': {
                'weather': constants.WEATHER_OPTIONS, 'lighting': constants.LIGHTING_OPTIONS,
                'workspace': constants.WORKSPACE_OPTIONS, 'operational_tempo': constants.OPERATIONAL_TEMPO_OPTIONS,
            },
            'imsafe_checklist': constants.IMSAFE_CHECKLIST,
            'personnel_roles': constants.PERSONNEL_ROLES,
            'default_mission_statement': constants.DEFAULT_MISSION_STATEMENT,
            'likelihoods': {str(k): v for k, v in risk.LIKELIHOODS.items()},
            'severities': risk.SEVERITIES,
            'matrix': {'red': sorted(risk.RED), 'yellow': sorted(risk.YELLOW), 'green': sorted(risk.GREEN)},
            'authority_tiers': [
                {'code': code, 'label': risk.AUTHORITY_LABELS[code], 'range': risk.AUTHORITY_RANGE_LABELS[code], 'max_percent': upper}
                for upper, code in risk.AUTHORITY_TIERS
            ],
        })


class MeView(BadInputAs400, APIView):
    """What the current user can do in MRM — the frontend uses this to show/hide controls."""

    permission_classes = [MRMAccess]

    def get(self, request):
        user = request.user
        scope = access.scope_unit_ids(user)
        return Response({
            'authority': access.authority(user),
            'designation': user.mrm_designation,
            'has_signature': bool(user.signature),
            'unit': str(user.unit_id) if user.unit_id else None,
            'can_author': access.can_author(user),
            'can_manage_registry': access.can_manage_registry(user),
            'is_admin': access.is_admin(user),
            'is_safety_officer': access.is_uso(user),
            'sees_all_units': scope is None or user.role == User.Role.COMMANDER,
            'scope_units': None if scope is None else [str(u) for u in scope],
        })


class SignatureView(BadInputAs400, APIView):
    permission_classes = [MRMAccess]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        if not request.user.signature:
            raise NotFound('No signature uploaded.')
        return FileResponse(request.user.signature.open('rb'))

    def post(self, request):
        upload = validate_image_upload(request.FILES.get('signature'))
        user = request.user
        if user.signature:
            user.signature.delete(save=False)
        user.signature.save(f'{user.username}_signature.{"png" if upload.content_type == "image/png" else "jpg"}', upload, save=True)
        log_action(user=user, action=AuditLog.Action.UPDATE, instance=user, description='Uploaded MRM signature', request=request)
        return Response({'has_signature': True})

    def delete(self, request):
        user = request.user
        if user.signature:
            user.signature.delete(save=False)
            user.signature = None
            user.save(update_fields=['signature'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkQueueView(BadInputAs400, APIView):
    """Counts for the 'what needs my attention' dashboard/sidebar badges."""

    permission_classes = [MRMAccess]

    def get(self, request):
        user = request.user
        forms = MRMForm.objects.filter(is_active=True)
        R = MRMForm.ReviewStatus
        data = {
            'my_drafts': forms.filter(created_by=user, status=MRMForm.Status.DRAFT).count(),
            'needs_revision': forms.filter(created_by=user, status=MRMForm.Status.REVIEWED, review_status__in=[R.REJECTED, R.NEEDS_REVISION]).count(),
            'awaiting_my_review': forms.filter(reviewed_by=user, status=MRMForm.Status.SUBMITTED, review_status=R.PENDING).count(),
            'awaiting_my_approval': forms.filter(
                authority_assigned_to=user, status=MRMForm.Status.REVIEWED, review_status=R.APPROVED, authority_approved=False,
            ).count(),
        }
        # Mission planning: missions waiting on this user's decision, and MRMs this user was asked to prepare.
        from apps.missions.models import Mission

        pending_missions = Mission.objects.filter(is_active=True, approval_authority=user, approval_status=Mission.ApprovalStatus.PENDING)
        data['missions_awaiting_my_approval'] = pending_missions.count()
        to_prepare = Mission.objects.filter(
            is_active=True, mrm_assignee__linked_account=user,
            approval_status__in=[Mission.ApprovalStatus.PENDING, Mission.ApprovalStatus.APPROVED],
        ).exclude(mrm_forms__is_active=True)
        data['mrm_to_prepare'] = to_prepare.count()

        tagged = forms.filter(
            tagged_personnel__user=user, tagged_personnel__is_active=True, authority_approved=True, feedback_collection_closed=False,
        ).exclude(feedback_items__user=user)
        data['feedback_to_give'] = tagged.distinct().count()

        needs_assignment = forms.filter(
            status=MRMForm.Status.REVIEWED, review_status=R.APPROVED, authority_approved=False, authority_assigned_to__isnull=True,
        )
        pending_feedback = MRMFeedback.objects.filter(status=MRMFeedback.Status.PENDING)
        scope = access.scope_unit_ids(user)
        if scope is not None:
            if access.is_uso(user):
                needs_assignment = needs_assignment.filter(unit_id__in=scope)
                pending_feedback = pending_feedback.filter(mrm__unit_id__in=scope)
            else:
                needs_assignment = needs_assignment.none()
                pending_feedback = pending_feedback.filter(mrm__reviewed_by=user) if access.is_evaluator(user) else pending_feedback.none()
        if access.is_admin(user) or access.is_uso(user):
            data['needs_authority_assignment'] = needs_assignment.count()
        data['feedback_to_review'] = pending_feedback.count()
        data['total_action_items'] = sum(
            data[k] for k in ('needs_revision', 'awaiting_my_review', 'awaiting_my_approval', 'feedback_to_give',
                              'missions_awaiting_my_approval', 'mrm_to_prepare')
        )
        return Response(data)


# ---------------------------------------------------------------------------
# Hazard registry
# ---------------------------------------------------------------------------

def _resolve_hazard_unit(user, unit_id):
    if unit_id and (access.is_admin(user) or access.is_uso(user)):
        unit = Unit.objects.filter(pk=unit_id, is_active=True).first()
        if unit is None:
            raise ValidationError({'unit': 'Unit not found.'})
        if not access.unit_in_scope(user, unit.id):
            raise PermissionDenied('That unit is outside your scope.')
        return unit
    if user.unit_id is None:
        raise ValidationError({'unit': 'Your account has no unit — an administrator must assign you to one first.'})
    return user.unit


def _filter_hazards(request, qs):
    p = request.query_params
    if p.get('search'):
        qs = qs.filter(Q(hazard_description__icontains=p['search']) | Q(activity_code__icontains=p['search']))
    if p.get('activity_code'):
        qs = qs.filter(activity_code=p['activity_code'])
    if p.get('unit'):
        qs = qs.filter(unit_id=p['unit'])
    level = (p.get('risk_level') or '').lower()
    if level == 'high':
        qs = qs.filter(after_risk_rating__in=risk.RED)
    elif level == 'medium':
        qs = qs.filter(after_risk_rating__in=risk.YELLOW)
    elif level == 'low':
        qs = qs.filter(after_risk_rating__in=risk.GREEN)
    return qs


class HazardViewSet(BadInputAs400, viewsets.GenericViewSet):
    """Hazard registry. Read: every MRM user (own unit). Write: Administrator, Evaluator, Unit Safety Officer."""

    permission_classes = [MRMAccess]
    serializer_class = HazardSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        return access.visible_hazards(self.request.user).select_related('unit', 'created_by')

    def list(self, request):
        qs = _filter_hazards(request, self.get_queryset()).order_by('-updated_at')
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    def retrieve(self, request, pk=None):
        return Response(self.get_serializer(self.get_object()).data)

    def create(self, request):
        if not access.can_manage_registry(request.user):
            raise PermissionDenied('You do not have permission to add hazards.')
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        unit = _resolve_hazard_unit(request.user, request.data.get('unit'))
        hazard = serializer.save(unit=unit, created_by=request.user)
        log_action(user=request.user, action=AuditLog.Action.CREATE, instance=hazard,
                   description=f'Added hazard "{hazard.hazard_description[:60]}" ({hazard.activity_code})', request=request)
        return Response(self.get_serializer(hazard).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        hazard = self.get_object()
        if not access.can_write_hazard(request.user, hazard):
            raise PermissionDenied('You can only edit hazards from your own unit.')
        serializer = self.get_serializer(hazard, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        hazard = serializer.save()
        log_action(user=request.user, action=AuditLog.Action.UPDATE, instance=hazard,
                   description=f'Updated hazard "{hazard.hazard_description[:60]}"', request=request)
        return Response(self.get_serializer(hazard).data)

    update = partial_update

    def destroy(self, request, pk=None):
        hazard = self.get_object()
        if not access.can_write_hazard(request.user, hazard):
            raise PermissionDenied('You can only delete hazards from your own unit.')
        if hazard.mrm_links.exists():
            raise ValidationError({'detail': 'Cannot delete hazard: it is being used in MRM forms.'})
        hazard.is_active = False
        hazard.save(update_fields=['is_active', 'updated_at'])
        log_action(user=request.user, action=AuditLog.Action.DELETE, instance=hazard,
                   description=f'Deleted hazard "{hazard.hazard_description[:60]}"', request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['post'], url_path='bulk-delete')
    def bulk_delete(self, request):
        if not access.can_manage_registry(request.user):
            raise PermissionDenied('You do not have permission to delete hazards.')
        ids = request.data.get('ids') or []
        if not isinstance(ids, list) or not ids:
            raise ValidationError({'ids': 'Select at least one hazard.'})
        deleted, skipped = 0, []
        for hazard in self.get_queryset().filter(id__in=ids):
            if not access.can_write_hazard(request.user, hazard):
                skipped.append({'id': str(hazard.id), 'reason': 'outside your unit'})
            elif hazard.mrm_links.exists():
                skipped.append({'id': str(hazard.id), 'reason': 'used in MRM forms'})
            else:
                hazard.is_active = False
                hazard.save(update_fields=['is_active', 'updated_at'])
                deleted += 1
        if deleted:
            log_action(user=request.user, action=AuditLog.Action.DELETE, description=f'Bulk-deleted {deleted} hazard(s)', request=request)
        return Response({'deleted': deleted, 'skipped': skipped})

    @action(detail=False, methods=['get'], url_path='activity-codes')
    def activity_codes(self, request):
        used = set(self.get_queryset().values_list('activity_code', flat=True))
        return Response(sorted(used | set(constants.ACTIVITY_CODES)))

    @action(detail=False, methods=['get'])
    def pickable(self, request):
        """Hazards a new/edited MRM may choose from: the unit's own registry plus its mother units'."""
        unit = _resolve_hazard_unit(request.user, request.query_params.get('unit')) if request.user.unit_id or request.query_params.get('unit') else None
        if unit is None:
            return Response({'count': 0, 'next': None, 'previous': None, 'results': []})
        qs = _filter_hazards(request, access.pickable_hazards(request.user, unit).select_related('unit', 'created_by'))
        page = self.paginate_queryset(qs.order_by('activity_code', 'hazard_description'))
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    @action(detail=False, methods=['get'])
    def export(self, request):
        qs = _filter_hazards(request, self.get_queryset()).order_by('unit__name', 'activity_code')
        response = HttpResponse(importers.export_hazards(qs), content_type=XLSX)
        response['Content-Disposition'] = f'attachment; filename="hazard_registry_{timezone.now():%Y%m%d}.xlsx"'
        return response

    @action(detail=False, methods=['get'], url_path='import-template')
    def import_template(self, request):
        response = HttpResponse(importers.import_template(), content_type=XLSX)
        response['Content-Disposition'] = 'attachment; filename="hazard_import_template.xlsx"'
        return response

    @action(detail=False, methods=['post'], url_path='import', parser_classes=[MultiPartParser, FormParser])
    def import_hazards(self, request):
        if not access.can_manage_registry(request.user):
            raise PermissionDenied('You do not have permission to import hazards.')
        upload = request.FILES.get('file')
        if upload is None or not upload.name.lower().endswith('.xlsx'):
            raise ValidationError({'file': 'Upload an .xlsx file.'})
        if upload.size > 5 * 1024 * 1024:
            raise ValidationError({'file': 'File must be 5 MB or smaller.'})
        unit = _resolve_hazard_unit(request.user, request.data.get('unit'))
        overwrite = str(request.data.get('overwrite', '')).lower() in ('1', 'true', 'on', 'yes')
        result = importers.import_hazards(upload, unit, request.user, overwrite=overwrite)
        if result['errors'] and not (result['created'] or result['updated']):
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        log_action(user=request.user, action=AuditLog.Action.CREATE,
                   description=f'Imported hazards into {unit.code}: {result["created"]} new, {result["updated"]} updated', request=request)
        return Response(result)


# ---------------------------------------------------------------------------
# MRM forms
# ---------------------------------------------------------------------------

FORM_ORDERING = {'created_at', '-created_at', 'mrm_number', '-mrm_number', 'total_percent', '-total_percent', 'date_submitted', '-date_submitted'}


class FormViewSet(BadInputAs400, viewsets.GenericViewSet):
    permission_classes = [MRMAccess]
    parser_classes = [JSONParser]

    def get_queryset(self):
        return access.visible_forms(self.request.user).select_related('unit', 'mission', 'created_by', 'reviewed_by', 'authority_assigned_to')

    def _filtered(self, request, qs):
        p, user = request.query_params, request.user
        for param, field in (('status', 'status'), ('review_status', 'review_status'), ('risk_category', 'risk_category'),
                             ('authority_level', 'authority_level'), ('unit', 'unit_id'), ('mission', 'mission_id')):
            if p.get(param):
                qs = qs.filter(**{field: p[param]})
        if p.get('approved') in ('true', 'false'):
            qs = qs.filter(authority_approved=p['approved'] == 'true')
        if p.get('search'):
            term = p['search']
            qs = qs.filter(Q(mrm_number__icontains=term) | Q(activity_mission__icontains=term) | Q(creator_name__icontains=term))
        role = p.get('role')
        if role == 'created':
            qs = qs.filter(created_by=user)
        elif role == 'review':
            qs = qs.filter(reviewed_by=user)
        elif role == 'approve':
            qs = qs.filter(authority_assigned_to=user)
        elif role == 'tagged':
            qs = qs.filter(tagged_personnel__user=user, tagged_personnel__is_active=True)
        stage = p.get('stage')
        R = MRMForm.ReviewStatus
        if stage == 'draft':
            qs = qs.filter(status=MRMForm.Status.DRAFT)
        elif stage == 'awaiting_review':
            qs = qs.filter(status=MRMForm.Status.SUBMITTED)
        elif stage == 'awaiting_authority':
            qs = qs.filter(status=MRMForm.Status.REVIEWED, review_status=R.APPROVED, authority_approved=False)
        elif stage == 'needs_revision':
            qs = qs.filter(status=MRMForm.Status.REVIEWED, review_status__in=[R.REJECTED, R.NEEDS_REVISION])
        elif stage == 'approved':
            qs = qs.filter(authority_approved=True)
        ordering = p.get('ordering') or '-created_at'
        return qs.order_by(ordering if ordering in FORM_ORDERING else '-created_at').distinct()

    def _detail(self, form, **extra):
        form = MRMForm.objects.select_related('unit', 'mission', 'created_by', 'reviewed_by', 'authority_assigned_to').get(pk=form.pk)
        data = serialize_form_detail(form, self.request.user)
        data.update(extra)
        return data

    def get_object(self):
        try:
            return self.get_queryset().get(pk=self.kwargs['pk'])
        except (MRMForm.DoesNotExist, ValueError, DjangoValidationError):
            raise NotFound('MRM form not found.')

    # --- CRUD ------------------------------------------------------------
    def list(self, request):
        qs = self._filtered(request, self.get_queryset())
        page = self.paginate_queryset(qs)
        return self.get_paginated_response([serialize_form_list_item(f, request.user) for f in page])

    def retrieve(self, request, pk=None):
        return Response(self._detail(self.get_object()))

    def create(self, request):
        form = services.create_mrm(request.user, request.data, request)
        return Response(self._detail(form), status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        form = services.update_mrm(request.user, self.get_object(), request.data, request)
        return Response(self._detail(form))

    update = partial_update

    def destroy(self, request, pk=None):
        services.archive_mrm(request.user, self.get_object(), request)
        return Response(status=status.HTTP_204_NO_CONTENT)

    # --- editor helpers ---------------------------------------------------
    @action(detail=False, methods=['post'], url_path='calculate-risk')
    def calculate_risk(self, request):
        unit = _resolve_hazard_unit(request.user, request.data.get('unit'))
        return Response(services.preview_risk(request.user, unit, request.data.get('hazards')))

    @action(detail=False, methods=['get'])
    def evaluators(self, request):
        unit = _resolve_hazard_unit(request.user, request.query_params.get('unit'))
        return Response([
            {'id': str(u.id), 'name': u.display_name_with_rank, 'unit': u.unit.code if u.unit_id else None}
            for u in access.evaluator_candidates(unit, exclude_user=request.user)
        ])

    @action(detail=False, methods=['get'])
    def people(self, request):
        """Search active users in a unit (for tagging crew/personnel)."""
        if not (access.can_author(request.user) or access.is_uso(request.user)):
            raise PermissionDenied('Not allowed.')
        unit = _resolve_hazard_unit(request.user, request.query_params.get('unit'))
        qs = User.objects.filter(is_active=True, unit=unit).select_related('unit')
        term = (request.query_params.get('q') or '').strip()
        if term:
            qs = qs.filter(Q(username__icontains=term) | Q(first_name__icontains=term) | Q(last_name__icontains=term)
                           | Q(personnel_record__service_number__icontains=term))
        return Response([
            {'id': str(u.id), 'name': u.display_name_with_rank, 'username': u.username,
             'service_number': getattr(getattr(u, 'personnel_record', None), 'service_number', '')}
            for u in qs.order_by('last_name', 'first_name')[:20]
        ])

    # --- workflow ---------------------------------------------------------
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        form, signed = services.submit_mrm(request.user, self.get_object(), request)
        warnings = [] if signed else ['You have no signature on file — upload one and use "Sign" so the form can be printed signed.']
        return Response(self._detail(form, warnings=warnings))

    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        form, warning = services.review_mrm(
            request.user, self.get_object(), request.data.get('review_status'), request.data.get('review_notes', ''),
            auto_sign=bool(request.data.get('auto_sign', True)), request=request,
        )
        return Response(self._detail(form, warnings=[warning] if warning else []))

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        form, pdf_error = services.authority_approve(request.user, self.get_object(), request.data.get('comments', ''), request)
        warnings = [f'Approved, but the PDF could not be generated ({pdf_error}). An administrator can regenerate it.'] if pdf_error else []
        return Response(self._detail(form, warnings=warnings))

    @action(detail=True, methods=['post'], url_path='reassign-authority')
    def reassign_authority(self, request, pk=None):
        form = services.reassign_authority(request.user, self.get_object(), request.data.get('authority'), request)
        return Response(self._detail(form))

    @action(detail=True, methods=['post'], url_path='reassign-reviewer')
    def reassign_reviewer(self, request, pk=None):
        form = services.reassign_reviewer(request.user, self.get_object(), request.data.get('reviewer'), request)
        return Response(self._detail(form))

    @action(detail=True, methods=['get'], url_path='authority-candidates')
    def authority_candidates(self, request, pk=None):
        form = self.get_object()
        if not access.can_reassign_authority(form, request.user):
            raise PermissionDenied('Not allowed.')
        level = form.authority_level
        if level == 'OPERATOR':
            candidates = [form.created_by]
        elif level == 'SUPERVISOR':
            candidates = [form.reviewed_by]
        else:
            candidates = access.authority_candidates(form.creator_unit or form.unit, level, [form.created_by_id, form.reviewed_by_id])
        return Response({
            'required': risk.AUTHORITY_LABELS[level],
            'candidates': [{'id': str(u.id), 'name': u.display_name_with_rank, 'unit': u.unit.code if u.unit_id else None}
                           for u in candidates if u],
        })

    @action(detail=True, methods=['post'])
    def sign(self, request, pk=None):
        form, which = services.sign_mrm(request.user, self.get_object(), request)
        return Response(self._detail(form, signed_as=which))

    # --- documents ----------------------------------------------------------
    @action(detail=True, methods=['get'])
    def pdf(self, request, pk=None):
        form = self.get_object()
        if form.authority_approved and form.approved_pdf:
            try:
                return FileResponse(form.approved_pdf.open('rb'), content_type='application/pdf',
                                    filename=f'MRM_{form.mrm_number}.pdf')
            except FileNotFoundError:
                pass
        from .pdf import generate_pdf

        data = generate_pdf(form)
        response = HttpResponse(data, content_type='application/pdf')
        disposition = 'inline' if request.query_params.get('inline') else 'attachment'
        response['Content-Disposition'] = f'{disposition}; filename="MRM_{form.mrm_number}{"" if form.authority_approved else "_DRAFT"}.pdf"'
        return response

    @action(detail=True, methods=['post'], url_path='regenerate-pdf')
    def regenerate_pdf(self, request, pk=None):
        form = services.regenerate_pdf(request.user, self.get_object(), request)
        return Response(self._detail(form))

    # --- personnel & feedback ------------------------------------------------
    @action(detail=True, methods=['get', 'post'])
    def personnel(self, request, pk=None):
        form = self.get_object()
        if request.method == 'POST':
            services.tag_personnel(request.user, form, request.data.get('user'), request.data.get('role') or 'Crew Member', request)
            form = self.get_object()
        return Response(self._detail(form)['tagged_personnel'], status=status.HTTP_201_CREATED if request.method == 'POST' else 200)

    @action(detail=True, methods=['delete'], url_path=r'personnel/(?P<tag_id>[^/.]+)')
    def untag(self, request, pk=None, tag_id=None):
        services.untag_personnel(request.user, self.get_object(), tag_id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='close-feedback')
    def close_feedback(self, request, pk=None):
        services.close_feedback(request.user, self.get_object())
        return Response(self._detail(self.get_object()))

    @action(detail=True, methods=['get'])
    def remind(self, request, pk=None):
        form = self.get_object()
        if not access.can_manage_personnel(form, request.user):
            raise PermissionDenied('Not allowed.')
        pending = services.pending_feedback_reminders(form)
        return Response({'pending': [{'user': str(t.user_id), 'name': t.user.display_name_with_rank, 'role': t.role} for t in pending]})

    @action(detail=True, methods=['get', 'post'])
    def feedback(self, request, pk=None):
        form = self.get_object()
        if request.method == 'POST':
            fb = services.submit_feedback(request.user, form, request.data)
            return Response(serialize_feedback(fb, request.user), status=status.HTTP_201_CREATED)
        qs = form.feedback_items.select_related('user', 'mrm', 'mrm__unit', 'reviewed_by')
        if not (access.is_admin(request.user) or access.can_manage_personnel(form, request.user)):
            qs = qs.filter(user=request.user)
        return Response([serialize_feedback(fb, request.user) for fb in qs])


# ---------------------------------------------------------------------------
# Feedback inbox
# ---------------------------------------------------------------------------

class FeedbackViewSet(BadInputAs400, viewsets.GenericViewSet):
    permission_classes = [MRMAccess]

    def get_queryset(self):
        user = self.request.user
        qs = MRMFeedback.objects.filter(is_active=True).select_related('user', 'mrm', 'mrm__unit', 'reviewed_by')
        scope = access.scope_unit_ids(user)
        if scope is None:
            return qs
        if access.is_uso(user):
            return qs.filter(Q(mrm__unit_id__in=scope) | Q(user=user))
        if access.is_evaluator(user):
            return qs.filter(Q(mrm__reviewed_by=user) | Q(user=user))
        return qs.filter(user=user)

    def list(self, request):
        qs = self.get_queryset()
        if request.query_params.get('status'):
            qs = qs.filter(status=request.query_params['status'])
        if request.query_params.get('mrm'):
            qs = qs.filter(mrm_id=request.query_params['mrm'])
        page = self.paginate_queryset(qs.order_by('-submitted_at'))
        return self.get_paginated_response([serialize_feedback(fb, request.user) for fb in page])

    def retrieve(self, request, pk=None):
        fb = self.get_queryset().filter(pk=pk).first()
        if fb is None:
            raise NotFound('Feedback not found.')
        FeedbackNotification.objects.filter(feedback=fb, officer=request.user, is_read=False).update(is_read=True, read_at=timezone.now())
        return Response(serialize_feedback(fb, request.user))

    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        fb = self.get_queryset().filter(pk=pk).first()
        if fb is None:
            raise NotFound('Feedback not found.')
        fb, hazard = services.review_feedback(
            request.user, fb, request.data.get('action'), request.data.get('review_notes', ''),
            request.data.get('action_taken', ''), request.data.get('new_hazard'), request,
        )
        data = serialize_feedback(fb, request.user)
        data['created_hazard'] = str(hazard.id) if hazard else None
        return Response(data)

    @action(detail=False, methods=['get'], url_path='pending-count')
    def pending_count(self, request):
        user = request.user
        if access.is_uso(user) or access.is_admin(user) or access.is_evaluator(user):
            count = self.get_queryset().filter(status=MRMFeedback.Status.PENDING).exclude(user=user).count()
        else:
            count = MRMForm.objects.filter(
                is_active=True, authority_approved=True, feedback_collection_closed=False,
                tagged_personnel__user=user, tagged_personnel__is_active=True,
            ).exclude(feedback_items__user=user).distinct().count()
        return Response({'count': count})

    @action(detail=False, methods=['get'])
    def mine(self, request):
        """Dashboard for tagged personnel: approved missions awaiting their feedback + what they've already given."""
        user = request.user
        tagged = MRMForm.objects.filter(is_active=True, authority_approved=True, tagged_personnel__user=user,
                                        tagged_personnel__is_active=True).select_related('unit', 'mission').distinct()
        done = {fb.mrm_id: fb for fb in MRMFeedback.objects.filter(user=user).select_related('user', 'mrm', 'mrm__unit', 'reviewed_by')}
        pending = [f for f in tagged if f.id not in done and not f.feedback_collection_closed]
        return Response({
            'stats': {'total_tagged': tagged.count(), 'pending_feedback': len(pending), 'completed_feedback': len(done)},
            'pending': [serialize_form_list_item(f, user) for f in pending],
            'completed': [serialize_feedback(fb, user) for fb in done.values()],
        })


# ---------------------------------------------------------------------------
# Unit Safety Officer tools
# ---------------------------------------------------------------------------

class IsSafetyOfficerOrAdmin(MRMAccess):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and (access.is_admin(request.user) or access.is_uso(request.user))


class SafetyUserViewSet(BadInputAs400, viewsets.GenericViewSet):
    """Scoped account administration for Unit Safety Officers (users in the units they oversee)."""

    permission_classes = [IsSafetyOfficerOrAdmin]

    def get_queryset(self):
        qs = User.objects.select_related('unit').order_by('last_name', 'first_name')
        scope = access.scope_unit_ids(self.request.user)
        return qs if scope is None else qs.filter(unit_id__in=scope)

    @staticmethod
    def _brief(u):
        return {
            'id': str(u.id), 'username': u.username, 'full_name': u.full_name, 'email': u.email,
            'unit': u.unit.name if u.unit_id else None, 'mrm_authority': u.effective_mrm_authority,
            'mrm_designation': u.mrm_designation, 'is_active': u.is_active, 'has_signature': bool(u.signature),
            'last_login': u.last_login,
        }

    def list(self, request):
        qs, p = self.get_queryset(), request.query_params
        if p.get('search'):
            qs = qs.filter(Q(username__icontains=p['search']) | Q(first_name__icontains=p['search'])
                           | Q(last_name__icontains=p['search']) | Q(email__icontains=p['search']))
        if p.get('status') in ('active', 'inactive'):
            qs = qs.filter(is_active=p['status'] == 'active')
        if p.get('authority'):
            qs = qs.filter(mrm_authority=p['authority'])
        page = self.paginate_queryset(qs)
        return self.get_paginated_response([self._brief(u) for u in page])

    def _target(self, request, pk):
        target = self.get_queryset().filter(pk=pk).first()
        if target is None:
            raise NotFound('User not found in your units.')
        if target.pk == request.user.pk:
            raise ValidationError({'detail': 'You cannot perform this action on your own account.'})
        if target.is_superuser or target.effective_mrm_authority == User.MRMAuthority.ADMINISTRATOR:
            if not access.is_admin(request.user):
                raise PermissionDenied('Administrator accounts can only be managed by administrators.')
        return target

    @action(detail=True, methods=['post'], url_path='toggle-active')
    def toggle_active(self, request, pk=None):
        from apps.accounts import security

        target = self._target(request, pk)
        if target.is_active:
            security.assert_can_deactivate(target, request.user)
        before = security.snapshot(target)
        target.is_active = not target.is_active
        target.save(update_fields=['is_active'])
        log_action(user=request.user, action=AuditLog.Action.UPDATE, instance=target,
                   description=f'{"Activated" if target.is_active else "Deactivated"} user "{target.username}"',
                   metadata={'security_changes': security.changes(before, security.snapshot(target))}, request=request)
        return Response(self._brief(target))

    @action(detail=True, methods=['post'], url_path='reset-password')
    def reset_password(self, request, pk=None):
        target = self._target(request, pk)
        new_password, confirm = request.data.get('new_password'), request.data.get('confirm_password')
        if not new_password or new_password != confirm:
            raise ValidationError({'detail': 'Enter the new password twice, identically.'})
        try:
            password_validation.validate_password(new_password, target)
        except DjangoValidationError as exc:
            raise ValidationError({'new_password': list(exc.messages)})
        target.set_password(new_password)
        target.must_change_password = True  # the user chooses their own password at next login
        target.save(update_fields=['password', 'must_change_password'])
        log_action(user=request.user, action=AuditLog.Action.UPDATE, instance=target,
                   description=f'Reset password for "{target.username}"', request=request)
        return Response({'detail': f'Password reset for {target.username}. They must change it at next login.'})


class SafetyAssignmentViewSet(BadInputAs400, viewsets.ModelViewSet):
    """Which units each Unit Safety Officer oversees (administrators only)."""

    permission_classes = [MRMAccess]
    serializer_class = SafetyAssignmentSerializer
    queryset = SafetyOfficerAssignment.objects.select_related('user', 'unit').filter(is_active=True)

    def check_permissions(self, request):
        super().check_permissions(request)
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and not access.is_admin(request.user):
            raise PermissionDenied('Only administrators can change safety officer assignments.')
        if not (access.is_admin(request.user) or access.is_uso(request.user)):
            raise PermissionDenied('Not allowed.')

    def get_queryset(self):
        qs = super().get_queryset()
        return qs if access.is_admin(self.request.user) else qs.filter(user=self.request.user)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])


class UnitLogoViewSet(BadInputAs400, viewsets.GenericViewSet):
    """Logos printed on a unit's MRM PDFs. Admin: any unit. Safety officer: units in their scope."""

    permission_classes = [MRMAccess]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = UnitLogoSerializer

    def get_queryset(self):
        return UnitLogo.objects.filter(is_active=True).select_related('unit')

    def list(self, request):
        return Response(self.get_serializer(self.get_queryset(), many=True, context={'request': request}).data)

    @action(detail=True, methods=['get'])
    def image(self, request, pk=None):
        logo = self.get_queryset().filter(pk=pk).first()
        if logo is None:
            raise NotFound('Logo not found.')
        return FileResponse(logo.image.open('rb'))

    def create(self, request):
        unit = Unit.objects.filter(pk=request.data.get('unit'), is_active=True).first()
        if unit is None:
            raise ValidationError({'unit': 'Unit not found.'})
        if not (access.is_admin(request.user) or (access.is_uso(request.user) and access.unit_in_scope(request.user, unit.id))):
            raise PermissionDenied('You cannot manage logos for this unit.')
        upload = validate_image_upload(request.FILES.get('image'))
        logo = UnitLogo.objects.filter(unit=unit).first()
        if logo is None:
            logo = UnitLogo.objects.create(unit=unit, image=upload, uploaded_by=request.user)
        else:
            if logo.image:
                logo.image.delete(save=False)
            logo.image, logo.uploaded_by, logo.is_active = upload, request.user, True
            logo.save()
        return Response(self.get_serializer(logo, context={'request': request}).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, pk=None):
        logo = self.get_queryset().filter(pk=pk).first()
        if logo is None:
            raise NotFound('Logo not found.')
        if not (access.is_admin(request.user) or (access.is_uso(request.user) and access.unit_in_scope(request.user, logo.unit_id))):
            raise PermissionDenied('You cannot manage logos for this unit.')
        logo.image.delete(save=False)
        logo.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AnalyticsView(BadInputAs400, APIView):
    """Scoped MRM analytics for Administrators and Unit Safety Officers (replaces the legacy chart pages)."""

    permission_classes = [IsSafetyOfficerOrAdmin]

    def get(self, request):
        user, p = request.user, request.query_params
        forms = MRMForm.objects.filter(is_active=True)
        scope = access.scope_unit_ids(user)
        if scope is not None:
            forms = forms.filter(unit_id__in=scope)
        if p.get('unit'):
            if not access.unit_in_scope(user, p['unit']):
                raise PermissionDenied('That unit is outside your scope.')
            forms = forms.filter(unit_id__in=Unit.objects.get(pk=p['unit']).get_descendant_ids())
        if p.get('from'):
            forms = forms.filter(created_at__date__gte=p['from'])
        if p.get('to'):
            forms = forms.filter(created_at__date__lte=p['to'])

        approved = forms.filter(authority_approved=True)
        stage_counts = Counter()
        from .serializers import stage_of
        for f in forms.only('status', 'review_status', 'authority_approved', 'authority_assigned_to'):
            stage_counts[stage_of(f)] += 1

        by_month = Counter(f.created_at.strftime('%Y-%m') for f in forms.only('created_at'))
        hazard_usage = list(
            Hazard.objects.filter(mrm_links__mrm__in=forms)
            .annotate(uses=Count('mrm_links')).order_by('-uses')[:10]
            .values('activity_code', 'hazard_description', 'after_risk_rating', 'uses')
        )
        feedback = MRMFeedback.objects.filter(mrm__in=forms)
        ratings = feedback.aggregate(
            accuracy=Avg('risk_assessment_accuracy'), identification=Avg('hazard_identification_rating'),
            mitigation=Avg('mitigation_effectiveness'),
        )
        return Response({
            'totals': {'forms': forms.count(), 'approved': approved.count(), 'stages': dict(stage_counts)},
            'risk_category': dict(Counter(forms.exclude(risk_category='').values_list('risk_category', flat=True))),
            'authority_level': {risk.AUTHORITY_LABELS[k]: v for k, v in Counter(forms.exclude(authority_level='').values_list('authority_level', flat=True)).items()},
            'by_month': dict(sorted(by_month.items())),
            'by_unit': list(forms.values('unit__code', 'unit__name').annotate(count=Count('id')).order_by('-count')),
            'avg_completion_hours': round((approved.aggregate(a=Avg('completion_time_seconds'))['a'] or 0) / 3600, 1),
            'top_hazards': hazard_usage,
            'feedback': {
                'total': feedback.count(),
                'pending': feedback.filter(status=MRMFeedback.Status.PENDING).count(),
                'reviewed': feedback.filter(status=MRMFeedback.Status.REVIEWED).count(),
                'action_taken': feedback.filter(status=MRMFeedback.Status.ACTION_TAKEN).count(),
                'avg_ratings': {k: round(v, 2) if v else None for k, v in ratings.items()},
            },
        })
