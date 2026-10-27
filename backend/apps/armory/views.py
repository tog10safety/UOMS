from itertools import chain

from django.utils import timezone
from rest_framework import serializers as drf_serializers
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.audit import log_action
from apps.core.models import AuditLog
from apps.core.permissions import ModulePermissionMixin, UnitScopedQuerysetMixin
from apps.core.rbac import Action, Module

from .models import AmmunitionIssuance, AmmunitionStock, ArmoryInspection, Firearm, FirearmIssuance
from .serializers import (
    AmmunitionIssuanceSerializer,
    AmmunitionStockSerializer,
    ArmoryInspectionSerializer,
    FirearmIssuanceSerializer,
    FirearmReturnSerializer,
    FirearmSerializer,
)


class FirearmViewSet(ModulePermissionMixin, UnitScopedQuerysetMixin, viewsets.ModelViewSet):
    """Firearms registry, scoped by unit and RBAC-gated by the ARMORY module."""

    queryset = Firearm.objects.select_related('unit', 'accountable_personnel').all()
    serializer_class = FirearmSerializer
    permission_module = Module.ARMORY
    filterset_fields = ['status', 'unit', 'accountable_personnel', 'is_active']
    search_fields = ['serial_number', 'firearm_type', 'make', 'model']
    ordering_fields = ['serial_number', 'created_at']

    def perform_create(self, serializer):
        instance = serializer.save()
        log_action(
            user=self.request.user, action=AuditLog.Action.CREATE, instance=instance,
            description=f'Registered firearm {instance.serial_number}', request=self.request,
        )

    def perform_update(self, serializer):
        instance = serializer.save()
        log_action(
            user=self.request.user, action=AuditLog.Action.UPDATE, instance=instance,
            description=f'Updated firearm {instance.serial_number}', request=self.request,
        )

    def perform_destroy(self, instance):
        log_action(
            user=self.request.user, action=AuditLog.Action.DELETE, instance=instance,
            description=f'Deactivated firearm {instance.serial_number}', request=self.request,
        )
        instance.is_active = False
        instance.save(update_fields=['is_active'])


class AmmunitionStockViewSet(ModulePermissionMixin, UnitScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = AmmunitionStock.objects.select_related('unit').all()
    serializer_class = AmmunitionStockSerializer
    permission_module = Module.ARMORY
    filterset_fields = ['ammunition_type', 'unit', 'is_active']
    search_fields = ['ammunition_type', 'lot_number']
    ordering_fields = ['quantity_on_hand', 'created_at']

    def perform_create(self, serializer):
        instance = serializer.save()
        log_action(
            user=self.request.user, action=AuditLog.Action.CREATE, instance=instance,
            description=f'Added ammunition stock: {instance}', request=self.request,
        )


class FirearmIssuanceViewSet(ModulePermissionMixin, viewsets.ModelViewSet):
    """
    Firearm issuance/return. POST creates a new issuance (and flips the
    firearm to ISSUED); POST /{id}/return/ closes it out (and flips the
    firearm back to SERVICEABLE).
    """

    queryset = FirearmIssuance.objects.select_related('firearm', 'issued_to', 'issued_by').all()
    serializer_class = FirearmIssuanceSerializer
    permission_module = Module.ARMORY
    action_permission_map = {'create': Action.ISSUE, 'return_firearm': Action.RETURN}
    filterset_fields = ['firearm', 'issued_to', 'status']
    ordering_fields = ['issue_date', 'created_at']

    def perform_create(self, serializer):
        firearm = serializer.validated_data['firearm']
        if firearm.status != Firearm.Status.SERVICEABLE:
            raise drf_serializers.ValidationError(
                f'Firearm {firearm.serial_number} is not available for issue (status: {firearm.status}).'
            )
        instance = serializer.save(issued_by=self.request.user)
        firearm.status = Firearm.Status.ISSUED
        firearm.save(update_fields=['status'])

        log_action(
            user=self.request.user, action=AuditLog.Action.ISSUE, instance=instance,
            description=f'Issued firearm {firearm.serial_number} to {instance.issued_to.full_name}',
            request=self.request,
        )

    @action(detail=True, methods=['post'], url_path='return')
    def return_firearm(self, request, pk=None):
        issuance = self.get_object()
        if issuance.status == FirearmIssuance.Status.RETURNED:
            raise drf_serializers.ValidationError('This firearm has already been returned.')

        serializer = FirearmReturnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        issuance.status = FirearmIssuance.Status.RETURNED
        issuance.return_date = timezone.now()
        issuance.condition_on_return = serializer.validated_data['condition_on_return']
        issuance.remarks = (issuance.remarks + '\n' + serializer.validated_data['remarks']).strip()
        issuance.save(update_fields=['status', 'return_date', 'condition_on_return', 'remarks'])

        issuance.firearm.status = Firearm.Status.SERVICEABLE
        issuance.firearm.save(update_fields=['status'])

        log_action(
            user=request.user, action=AuditLog.Action.RETURN, instance=issuance,
            description=f'Returned firearm {issuance.firearm.serial_number} from {issuance.issued_to.full_name}',
            request=request,
        )
        return Response(FirearmIssuanceSerializer(issuance).data)


class AmmunitionIssuanceViewSet(ModulePermissionMixin, viewsets.ModelViewSet):
    """Issuing ammunition decrements the stock's quantity_on_hand."""

    queryset = AmmunitionIssuance.objects.select_related('ammunition_stock', 'issued_to', 'issued_by').all()
    serializer_class = AmmunitionIssuanceSerializer
    permission_module = Module.ARMORY
    action_permission_map = {'create': Action.ISSUE}
    filterset_fields = ['ammunition_stock', 'issued_to']
    ordering_fields = ['issue_date', 'created_at']

    def perform_create(self, serializer):
        instance = serializer.save(issued_by=self.request.user)
        stock = instance.ammunition_stock
        stock.quantity_on_hand -= instance.quantity
        stock.save(update_fields=['quantity_on_hand'])

        log_action(
            user=self.request.user, action=AuditLog.Action.ISSUE, instance=instance,
            description=f'Issued {instance.quantity} rounds of {stock.ammunition_type} to '
                        f'{instance.issued_to.full_name}',
            request=self.request,
        )


class ArmoryInspectionViewSet(ModulePermissionMixin, viewsets.ModelViewSet):
    queryset = ArmoryInspection.objects.select_related('firearm', 'inspected_by').all()
    serializer_class = ArmoryInspectionSerializer
    permission_module = Module.ARMORY
    filterset_fields = ['firearm', 'result']
    ordering_fields = ['inspection_date']

    def perform_create(self, serializer):
        instance = serializer.save()
        if instance.result == ArmoryInspection.Result.FAILED and instance.firearm:
            instance.firearm.status = Firearm.Status.UNSERVICEABLE
            instance.firearm.save(update_fields=['status'])
        elif instance.result == ArmoryInspection.Result.NEEDS_MAINTENANCE and instance.firearm:
            instance.firearm.status = Firearm.Status.IN_REPAIR
            instance.firearm.save(update_fields=['status'])

        log_action(
            user=self.request.user, action=AuditLog.Action.OTHER, instance=instance,
            description=f'Recorded armory inspection: {instance}', request=self.request,
        )


class ArmoryTransactionHistoryView(APIView):
    """
    Unified transaction history: merges firearm issuances/returns and
    ammunition issuances into a single chronological feed for the
    Armory Management "Transaction History" view.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        firearm_txns = [
            {
                'id': f'firearm-{i.id}',
                'type': 'FIREARM_ISSUE' if i.status != FirearmIssuance.Status.RETURNED else 'FIREARM_RETURN',
                'description': f'{i.firearm.serial_number} — {i.issued_to.full_name}',
                'quantity': 1,
                'date': i.return_date or i.issue_date,
            }
            for i in FirearmIssuance.objects.select_related('firearm', 'issued_to').order_by('-created_at')[:50]
        ]
        ammo_txns = [
            {
                'id': f'ammo-{i.id}',
                'type': 'AMMUNITION_ISSUE',
                'description': f'{i.ammunition_stock.ammunition_type} x{i.quantity} — {i.issued_to.full_name}',
                'quantity': i.quantity,
                'date': i.issue_date,
            }
            for i in AmmunitionIssuance.objects.select_related('ammunition_stock', 'issued_to').order_by('-created_at')[:50]
        ]
        merged = sorted(chain(firearm_txns, ammo_txns), key=lambda t: t['date'], reverse=True)
        return Response(merged[:50])
