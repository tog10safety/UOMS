from django.contrib.auth import get_user_model
from rest_framework import generics, status, viewsets
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.core.audit import log_action
from apps.core.models import AuditLog

from . import security
from apps.core.permissions import ModulePermissionMixin
from apps.core.rbac import Module

from .serializers import (
    ChangePasswordSerializer,
    ProfileUpdateSerializer,
    UOMSTokenObtainPairSerializer,
    UserCreateSerializer,
    UserSerializer,
)

User = get_user_model()


def _client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    return forwarded_for.split(',')[0].strip() if forwarded_for else request.META.get('REMOTE_ADDR')


class LoginView(TokenObtainPairView):
    """Issues JWT access/refresh tokens and records a LOGIN/LOGIN_FAILED audit entry."""

    serializer_class = UOMSTokenObtainPairSerializer
    throttle_scope = 'auth'

    def post(self, request, *args, **kwargs):
        username = request.data.get('username', '')
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception:
            attempted_user = User.objects.filter(username=username).first()
            log_action(
                user=attempted_user,
                action=AuditLog.Action.LOGIN_FAILED,
                description=f'Failed login attempt for username "{username}"',
                request=request,
            )
            raise

        user = serializer.user
        user.last_login_ip = _client_ip(request)
        user.save(update_fields=['last_login_ip'])
        log_action(user=user, action=AuditLog.Action.LOGIN, description='User logged in', request=request)

        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """Blacklists the supplied refresh token so it can no longer be used."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'detail': 'refresh token is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            return Response({'detail': 'Invalid or expired token.'}, status=status.HTTP_400_BAD_REQUEST)

        log_action(user=request.user, action=AuditLog.Action.LOGOUT, description='User logged out', request=request)
        return Response(status=status.HTTP_205_RESET_CONTENT)


class MeView(generics.RetrieveUpdateAPIView):
    """The current authenticated user's own profile."""

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        # Writes accept only the self-service profile fields — never role/unit/MRM authority.
        if self.request.method in ('PUT', 'PATCH'):
            return ProfileUpdateSerializer
        return UserSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(self.get_object()).data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'detail': 'Password updated successfully.'})


class UserViewSet(ModulePermissionMixin, viewsets.ModelViewSet):
    """
    CRUD for system user accounts & roles, gated by the ADMINISTRATION
    module permission (ADMIN always has full access; by default only
    COMMANDER additionally gets VIEW — configurable via RolePermission).

    Regular personnel records (rank, qualifications, assignment) live in
    apps.personnel — this endpoint manages *login accounts and RBAC role*
    only, per the "Account management / Role-based access control" scope
    of the Personnel Management module.
    """

    queryset = User.objects.all().order_by('username')
    permission_module = Module.ADMINISTRATION
    filterset_fields = ['role', 'unit', 'section', 'is_active']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['username', 'date_joined', 'role']

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        return UserSerializer

    def perform_create(self, serializer):
        user = serializer.save()
        log_action(
            user=self.request.user,
            action=AuditLog.Action.CREATE,
            instance=user,
            description=f'Created user account "{user.username}" with role {user.role}',
            metadata={'security_attributes': security.snapshot(user)},
            request=self.request,
        )

    def perform_update(self, serializer):
        instance = serializer.instance
        before = security.snapshot(instance)
        if instance.is_active and serializer.validated_data.get('is_active') is False:
            security.assert_can_deactivate(instance, self.request.user)
        user = serializer.save()
        changed = security.changes(before, security.snapshot(user))
        log_action(
            user=self.request.user,
            action=AuditLog.Action.UPDATE,
            instance=user,
            description=(
                f'Changed security attributes of "{user.username}": {", ".join(changed)}'
                if changed else f'Updated user account "{user.username}"'
            ),
            metadata={'security_changes': changed} if changed else None,
            request=self.request,
        )

    def perform_destroy(self, instance):
        security.assert_can_deactivate(instance, self.request.user)
        log_action(
            user=self.request.user,
            action=AuditLog.Action.DELETE,
            instance=instance,
            description=f'Deactivated user account "{instance.username}"',
            metadata={'security_changes': {'is_active': {'from': 'True', 'to': 'False'}}},
            request=self.request,
        )
        # Soft delete: never hard-delete an account with historical audit trail.
        instance.is_active = False
        instance.save(update_fields=['is_active'])
