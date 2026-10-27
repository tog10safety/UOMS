"""
Seeds the default module x action permission matrix for each non-ADMIN
role. ADMIN is intentionally not seeded here — it always passes every
check via User.role == 'ADMIN' / is_superuser in
apps.core.permissions.has_module_permission, per the "User Administrator
has full authority" requirement.

Safe to re-run: existing rows are updated in place, nothing is duplicated.

    python manage.py seed_permissions
"""
from django.core.management.base import BaseCommand

from apps.core.models import RolePermission
from apps.core.rbac import Action, DEFAULT_PERMISSION_MATRIX, Module


class Command(BaseCommand):
    help = 'Seed the default RolePermission matrix for COMMANDER/STAFF/OPERATOR/VIEWER.'

    def handle(self, *args, **options):
        created, updated = 0, 0

        for role, module_map in DEFAULT_PERMISSION_MATRIX.items():
            for module in Module.values:
                granted_actions = module_map.get(module, set())
                for action in Action.values:
                    _, was_created = RolePermission.objects.update_or_create(
                        role=role, module=module, action=action,
                        defaults={'is_granted': action in granted_actions},
                    )
                    created += was_created
                    updated += not was_created

        self.stdout.write(self.style.SUCCESS(
            f'Permission matrix seeded: {created} created, {updated} updated.'
        ))
