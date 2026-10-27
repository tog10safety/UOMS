"""
One-time data-migration helper for the User.unit CharField -> ForeignKey(Unit)
change. Run this once after `migrate` if you had existing users with a
free-text `unit` value under the old schema:

    python manage.py migrate_user_units

It never deletes `unit_legacy` (kept for audit/reference) and never
overwrites a `unit` that's already set.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.personnel.models import Unit

User = get_user_model()


class Command(BaseCommand):
    help = 'Map legacy free-text User.unit_legacy values onto the real Unit foreign key.'

    def handle(self, *args, **options):
        candidates = User.objects.filter(unit__isnull=True).exclude(unit_legacy='')
        matched, unmatched = 0, []

        for user in candidates:
            unit = Unit.objects.filter(
                Q(name__iexact=user.unit_legacy) | Q(code__iexact=user.unit_legacy)
            ).first()
            if unit:
                user.unit = unit
                user.save(update_fields=['unit'])
                matched += 1
            else:
                unmatched.append(f'{user.username} (unit_legacy="{user.unit_legacy}")')

        self.stdout.write(self.style.SUCCESS(f'Matched {matched} user(s) to an existing Unit.'))
        if unmatched:
            self.stdout.write(self.style.WARNING(
                f'{len(unmatched)} user(s) had no matching Unit by name/code — assign manually:'
            ))
            for line in unmatched:
                self.stdout.write(f'  - {line}')
