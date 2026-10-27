"""
Role-based access control (RBAC) permission classes.

UOMS defines a fixed set of roles on the User model (see apps.accounts.models.User.Role).
These permission classes let views declare "who is allowed" declaratively,
e.g. `permission_classes = [IsAdminOrCommander]`.
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS


class HasRole(BasePermission):
    """Base class: allow access only to users whose `.role` is in `allowed_roles`."""

    allowed_roles: tuple = ()

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user.is_superuser or user.role in self.allowed_roles)
        )


class IsAdmin(HasRole):
    allowed_roles = ('ADMIN',)


class IsAdminOrCommander(HasRole):
    allowed_roles = ('ADMIN', 'COMMANDER')


class IsAdminCommanderOrStaff(HasRole):
    allowed_roles = ('ADMIN', 'COMMANDER', 'STAFF')


class ReadOnlyOrAdmin(BasePermission):
    """Anyone authenticated can read; only ADMIN/COMMANDER can write."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.is_superuser or request.user.role in ('ADMIN', 'COMMANDER')


class ReadOnlyOrStaffUp(BasePermission):
    """Anyone authenticated can read; ADMIN/COMMANDER/STAFF can write. Used for day-to-day supply/inventory work."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.is_superuser or request.user.role in ('ADMIN', 'COMMANDER', 'STAFF')


class IsSelfOrAdmin(BasePermission):
    """Object-level permission: user may view/edit their own record, admins may edit any."""

    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser or request.user.role == 'ADMIN':
            return True
        owner = getattr(obj, 'user', obj)
        return owner == request.user


# ---------------------------------------------------------------------------
# Granular module x action RBAC (see apps.core.rbac and apps.core.models.RolePermission)
# ---------------------------------------------------------------------------

def has_module_permission(user, module, action):
    """
    True if `user` may perform `action` on `module`, per the RolePermission
    matrix. Superusers and ADMIN-role users always pass — ADMIN retains
    full authority over the entire system regardless of the configured
    matrix, per the User Administrator requirement.
    """
    from apps.core.models import RolePermission  # local import: avoids a models<->permissions import cycle

    if not (user and user.is_authenticated):
        return False
    if user.is_superuser or user.role == 'ADMIN':
        return True
    return RolePermission.objects.filter(
        role=user.role, module=module, action=action, is_granted=True,
    ).exists()


class HasModulePermission(BasePermission):
    """
    Generic DRF permission class driven by two attributes the view sets:

      permission_module: an apps.core.rbac.Module value, e.g. Module.VEHICLES
      action_permission_map: optional dict of {DRF view.action: Action},
        for custom actions (e.g. {'depart': Action.DISPATCH, 'return_firearm': Action.RETURN}).
        Standard list/retrieve/create/update/partial_update/destroy fall
        back to apps.core.rbac.METHOD_DEFAULT_ACTION based on HTTP method.

    This is the backend half of RBAC enforcement — the frontend hides
    buttons the user can't use, but this class is what actually rejects
    an unauthorized request regardless of how it was made.
    """

    def has_permission(self, request, view):
        from apps.core.rbac import METHOD_DEFAULT_ACTION

        user = request.user
        if not (user and user.is_authenticated):
            return False

        module = getattr(view, 'permission_module', None)
        if module is None:
            # A view that forgot to declare permission_module fails closed, not open.
            return False

        # Priority: an explicit override (plain APIViews that aren't
        # ViewSets set this directly) > the action_permission_map lookup
        # by DRF ViewSet action name > the HTTP-method default.
        explicit_action = getattr(view, 'required_action', None)
        action_map = getattr(view, 'action_permission_map', {})
        drf_action = getattr(view, 'action', None)
        action = explicit_action or action_map.get(drf_action) or METHOD_DEFAULT_ACTION.get(request.method)
        if action is None:
            return False

        return has_module_permission(user, module, action)


class ModulePermissionMixin:
    """
    Mixin for ViewSets: declares `permission_module` and applies
    HasModulePermission automatically. Subclasses only need to set:

        permission_module = Module.VEHICLES
        action_permission_map = {'dispatch': Action.DISPATCH}  # optional, for custom @action methods

    Unit/section-based queryset scoping is applied by UnitScopedQuerysetMixin
    (see below) — combine both mixins on views that need row-level scoping.
    """

    permission_classes = [HasModulePermission]
    permission_module = None
    action_permission_map = {}


class UnitScopedQuerysetMixin:
    """
    Restricts list/retrieve results to the requesting user's unit AND every
    unit subordinate to it in the echelon hierarchy (HPAF > Command > Wing >
    Group > Squadron) — a "mother unit" user sees its own records plus every
    unit beneath it, per Unit.get_descendant_ids(). Bypassed entirely for
    ADMIN/COMMANDER/superuser, who see all units. Subclasses set:

        unit_field = 'unit'  # the queryset lookup path to a Unit FK,
                              # e.g. 'assigned_driver__unit' if the model
                              # itself has no direct unit field.

    A user with no unit assigned and no cross-unit role sees an empty
    queryset rather than everything — fail closed, not open.
    """

    unit_field = 'unit'

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        if user.is_superuser or user.role in ('ADMIN', 'COMMANDER'):
            return queryset
        if not user.unit_id:
            return queryset.none()
        visible_unit_ids = user.unit.get_descendant_ids(include_self=True)
        return queryset.filter(**{f'{self.unit_field}__in': visible_unit_ids})
