from django.core.management.base import BaseCommand

from apps.missions.models import Mission
from apps.mrm.services import expected_mission_review_status


class Command(BaseCommand):
    help = (
        "Verify that every mission's stored risk-review status equals what its MRM form implies. "
        'The MRM is authoritative; the Mission column is a read-only projection kept only until it is dropped. '
        'Use --fix to rewrite any projection that drifted.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--fix', action='store_true')

    def handle(self, *args, **opts):
        drift = 0
        for mission in Mission.objects.filter(is_active=True).prefetch_related('mrm_forms'):
            form = mission.active_mrm
            if form is None:
                continue
            expected = expected_mission_review_status(form)
            if mission.risk_review_status != expected:
                drift += 1
                self.stdout.write(f'{mission.name}: stored {mission.risk_review_status}, MRM {form.mrm_number} implies {expected}')
                if opts['fix']:
                    mission.risk_review_status = expected
                    mission.save(update_fields=['risk_review_status', 'updated_at'])
        self.stdout.write(self.style.SUCCESS('No drift.') if not drift else self.style.WARNING(f'{drift} mission(s) drifted' + (' — fixed.' if opts['fix'] else '.')))
