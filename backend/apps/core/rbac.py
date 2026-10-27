"""
Granular RBAC: module x action permission matrix.

This sits alongside (not instead of) the existing User.role field.
Role still identifies "what kind of user this is"; RolePermission is the
configurable matrix of what each role may do, per module, per action —
this is what apps.core.permissions.HasModulePermission checks against.
"""
from django.db import models


class Module(models.TextChoices):
    DASHBOARD = 'DASHBOARD', 'Dashboard'
    PERSONNEL = 'PERSONNEL', 'Personnel Management'
    VEHICLES = 'VEHICLES', 'Vehicle Tracking and Monitoring'
    AIRCRAFT = 'AIRCRAFT', 'Aircraft Flying Monitoring'
    MISSIONS = 'MISSIONS', 'Mission Risk Management'
    ARMORY = 'ARMORY', 'Armory Management'
    INVENTORY = 'INVENTORY', 'Inventory Management'
    GIS = 'GIS', 'GIS / Operational Mapping'
    REPORTS = 'REPORTS', 'Reports'
    ADMINISTRATION = 'ADMINISTRATION', 'System Administration'


class Action(models.TextChoices):
    VIEW = 'VIEW', 'View'
    CREATE = 'CREATE', 'Create'
    EDIT = 'EDIT', 'Edit'
    DELETE = 'DELETE', 'Delete / Archive'
    APPROVE = 'APPROVE', 'Approve'
    DISPATCH = 'DISPATCH', 'Dispatch'
    ISSUE = 'ISSUE', 'Issue'
    RETURN = 'RETURN', 'Return'
    ASSIGN = 'ASSIGN', 'Assign'
    EXPORT = 'EXPORT', 'Export'
    REPORT = 'REPORT', 'Report'


# Default seed matrix: role -> module -> set of granted actions.
# ADMIN is always fully granted (checked in code, not listed here) since
# it's also gated by User.is_superuser as a hard bypass.
_ALL_ACTIONS = set(Action.values)
_BASIC_RW = {Action.VIEW, Action.CREATE, Action.EDIT}
_VIEW_ONLY = {Action.VIEW, Action.REPORT, Action.EXPORT}

DEFAULT_PERMISSION_MATRIX = {
    'COMMANDER': {
        Module.DASHBOARD: _ALL_ACTIONS,
        Module.PERSONNEL: _ALL_ACTIONS - {Action.DELETE},
        Module.VEHICLES: _ALL_ACTIONS - {Action.DELETE},
        Module.AIRCRAFT: _ALL_ACTIONS - {Action.DELETE},
        Module.MISSIONS: _ALL_ACTIONS,
        Module.ARMORY: _ALL_ACTIONS - {Action.DELETE},
        Module.INVENTORY: _ALL_ACTIONS - {Action.DELETE},
        Module.GIS: _ALL_ACTIONS - {Action.DELETE},
        Module.REPORTS: _VIEW_ONLY,
        Module.ADMINISTRATION: {Action.VIEW},
    },
    'STAFF': {
        Module.DASHBOARD: {Action.VIEW},
        Module.PERSONNEL: _BASIC_RW,
        Module.VEHICLES: _BASIC_RW | {Action.DISPATCH, Action.ASSIGN},
        Module.AIRCRAFT: _BASIC_RW | {Action.ASSIGN},
        Module.MISSIONS: _BASIC_RW,
        Module.ARMORY: _BASIC_RW | {Action.ISSUE, Action.RETURN},
        Module.INVENTORY: _BASIC_RW | {Action.ISSUE, Action.RETURN, Action.ASSIGN},
        Module.GIS: _BASIC_RW,
        Module.REPORTS: _VIEW_ONLY,
        Module.ADMINISTRATION: set(),
    },
    'OPERATOR': {
        Module.DASHBOARD: {Action.VIEW},
        Module.PERSONNEL: {Action.VIEW},
        Module.VEHICLES: {Action.VIEW, Action.DISPATCH},
        Module.AIRCRAFT: {Action.VIEW},
        Module.MISSIONS: {Action.VIEW},
        Module.ARMORY: {Action.VIEW, Action.ISSUE, Action.RETURN},
        Module.INVENTORY: {Action.VIEW, Action.ISSUE, Action.RETURN},
        Module.GIS: {Action.VIEW},
        Module.REPORTS: {Action.VIEW},
        Module.ADMINISTRATION: set(),
    },
    'VIEWER': {
        Module.DASHBOARD: {Action.VIEW},
        Module.PERSONNEL: {Action.VIEW},
        Module.VEHICLES: {Action.VIEW},
        Module.AIRCRAFT: {Action.VIEW},
        Module.MISSIONS: {Action.VIEW},
        Module.ARMORY: {Action.VIEW},
        Module.INVENTORY: {Action.VIEW},
        Module.GIS: {Action.VIEW},
        Module.REPORTS: {Action.VIEW},
        Module.ADMINISTRATION: set(),
    },
}

# HTTP-method -> default action, for standard CRUD endpoints that don't
# declare an explicit action_permission_map entry for the current DRF action.
METHOD_DEFAULT_ACTION = {
    'GET': Action.VIEW, 'HEAD': Action.VIEW, 'OPTIONS': Action.VIEW,
    'POST': Action.CREATE, 'PUT': Action.EDIT, 'PATCH': Action.EDIT, 'DELETE': Action.DELETE,
}
