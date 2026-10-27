from rest_framework import viewsets

from apps.core.audit import log_action
from apps.core.models import AuditLog
from apps.core.permissions import ModulePermissionMixin, UnitScopedQuerysetMixin
from apps.core.rbac import Module

from .models import Personnel, Position, Qualification, Rank, Section, Unit
from .serializers import (
    PersonnelDetailSerializer,
    PersonnelListSerializer,
    PositionSerializer,
    QualificationSerializer,
    RankSerializer,
    SectionSerializer,
    UnitSerializer,
)


class ReferenceDataViewSet(ModulePermissionMixin, viewsets.ModelViewSet):
    """Base for small lookup tables (Rank/Unit/Position/Qualification/Section)."""

    permission_module = Module.PERSONNEL
    search_fields = ['name']
    ordering_fields = ['name']


class RankViewSet(ReferenceDataViewSet):
    queryset = Rank.objects.all()
    serializer_class = RankSerializer
    ordering_fields = ['order', 'name']


class UnitViewSet(ReferenceDataViewSet):
    queryset = Unit.objects.select_related('parent_unit').all()
    serializer_class = UnitSerializer
    filterset_fields = ['parent_unit', 'is_active']


class SectionViewSet(ReferenceDataViewSet):
    queryset = Section.objects.select_related('unit').all()
    serializer_class = SectionSerializer
    filterset_fields = ['unit', 'is_active']


class PositionViewSet(ReferenceDataViewSet):
    queryset = Position.objects.all()
    serializer_class = PositionSerializer


class QualificationViewSet(ReferenceDataViewSet):
    queryset = Qualification.objects.all()
    serializer_class = QualificationSerializer


class PersonnelViewSet(ModulePermissionMixin, UnitScopedQuerysetMixin, viewsets.ModelViewSet):
    """Full CRUD over Personnel records, scoped by RBAC and unit, filterable by unit/status."""

    queryset = Personnel.objects.select_related('rank', 'unit', 'position', 'linked_account').prefetch_related('qualifications')
    permission_module = Module.PERSONNEL
    filterset_fields = ['unit', 'rank', 'position', 'status', 'is_active']
    search_fields = ['service_number', 'first_name', 'last_name', 'email']
    ordering_fields = ['last_name', 'created_at', 'status']

    def get_serializer_class(self):
        if self.action == 'list':
            return PersonnelListSerializer
        return PersonnelDetailSerializer

    def perform_create(self, serializer):
        instance = serializer.save()
        log_action(
            user=self.request.user,
            action=AuditLog.Action.CREATE,
            instance=instance,
            description=f'Created personnel record for {instance.full_name}',
            request=self.request,
        )

    def perform_update(self, serializer):
        instance = serializer.save()
        log_action(
            user=self.request.user,
            action=AuditLog.Action.UPDATE,
            instance=instance,
            description=f'Updated personnel record for {instance.full_name}',
            request=self.request,
        )

    def perform_destroy(self, instance):
        log_action(
            user=self.request.user,
            action=AuditLog.Action.DELETE,
            instance=instance,
            description=f'Deactivated personnel record for {instance.full_name}',
            request=self.request,
        )
        instance.is_active = False
        instance.save(update_fields=['is_active'])
