from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.accounts.models import User


class UOMSTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Adds role/unit claims to the JWT and blocks inactive accounts."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['role'] = user.role
        token['unit'] = user.unit.code if user.unit else None
        token['section'] = user.section.name if user.section else None
        token['full_name'] = user.full_name
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        if not self.user.is_active:
            raise serializers.ValidationError('This account has been deactivated.')
        data['user'] = UserSerializer(self.user).data
        return data


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    unit_name = serializers.CharField(source='unit.name', read_only=True, default=None)
    section_name = serializers.CharField(source='section.name', read_only=True, default=None)
    permissions = serializers.SerializerMethodField()
    has_signature = serializers.SerializerMethodField()
    effective_mrm_authority = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'full_name',
            'role', 'unit', 'unit_name', 'section', 'section_name', 'permissions',
            'phone_number', 'is_active', 'must_change_password',
            'mrm_authority', 'mrm_designation', 'effective_mrm_authority', 'has_signature',
            'last_login', 'date_joined',
        ]
        read_only_fields = ['id', 'last_login', 'date_joined']

    def get_has_signature(self, obj):
        return bool(obj.signature)

    def get_permissions(self, obj):
        """
        The full module x action grant map for this user's role, so the
        frontend can decide what to show without hard-coding role logic —
        it should still never be trusted as the authorization boundary
        (the API enforces that independently via HasModulePermission).
        """
        from apps.core.models import RolePermission
        from apps.core.rbac import Action, Module

        if obj.is_superuser or obj.role == User.Role.ADMIN:
            return {module: list(Action.values) for module in Module.values}

        grants = {}
        for row in RolePermission.objects.filter(role=obj.role, is_granted=True):
            grants.setdefault(row.module, []).append(row.action)
        return grants


class ProfileUpdateSerializer(serializers.ModelSerializer):
    """
    The only fields a user may change about *themselves* via PATCH /auth/me/.
    Role, unit, MRM authority/designation and account status are administrator-managed.
    """

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone_number']


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'unit', 'section', 'phone_number', 'password', 'is_active',
            'mrm_authority', 'mrm_designation',
        ]
        read_only_fields = ['id']

    def validate_password(self, value):
        try:
            password_validation.validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.must_change_password = True
        user.save()
        return user


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        try:
            password_validation.validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value

    def validate_current_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Current password is incorrect.')
        return value

    def save(self, **kwargs):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.must_change_password = False
        user.save(update_fields=['password', 'must_change_password'])
        return user
