from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MissionPlanningMigrationSafetyTests(TransactionTestCase):
    """Missions that existed before categories keep their data and stay valid under the new constraints."""

    before = [('missions', '0001_initial')]
    after = [('missions', '0002_mission_planning')]

    def migrate(self, targets):
        MigrationExecutor(connection).migrate(targets)
        return MigrationExecutor(connection).loader.project_state(targets).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_existing_missions_survive_and_get_safe_defaults(self):
        old = self.migrate(self.before)
        Mission = old.get_model('missions', 'Mission')
        legacy = Mission.objects.create(name='Pre-existing mission', status='ONGOING', risk_review_status='APPROVED')   # no dates at all

        new = self.migrate(self.after)
        Mission = new.get_model('missions', 'Mission')
        row = Mission.objects.get(pk=legacy.pk)
        self.assertEqual((row.name, row.status, row.risk_review_status), ('Pre-existing mission', 'ONGOING', 'APPROVED'))
        self.assertEqual((row.category, row.approval_status), ('', 'DRAFT'))        # uncategorised legacy, not silently reclassified
        self.assertIsNone(row.client_request_id)

    def test_legacy_rows_without_dates_are_exempt_from_the_schedule_constraint(self):
        new = self.migrate(self.after)
        Mission = new.get_model('missions', 'Mission')
        Mission.objects.create(name='Legacy without dates', category='')            # must not violate mission_schedule_valid_when_categorised

    def test_migration_reverses_without_losing_missions(self):
        new = self.migrate(self.after)
        Mission = new.get_model('missions', 'Mission')
        keep = Mission.objects.create(name='Keep me')
        old = self.migrate(self.before)
        self.assertTrue(old.get_model('missions', 'Mission').objects.filter(pk=keep.pk).exists())
