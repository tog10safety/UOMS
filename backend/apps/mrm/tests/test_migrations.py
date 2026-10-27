from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class AccountsMigrationSafetyTests(TransactionTestCase):
    """Test H — existing accounts survive the MRM migrations, and the migrations are reversible."""

    before = [('accounts', '0002_initial')]
    after = [('accounts', '0003_mrm_authority_designation_signature')]

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return MigrationExecutor(connection).loader.project_state(targets).apps

    def tearDown(self):
        # leave the schema at the latest state for any test that runs after this one
        MigrationExecutor(connection).migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())

    def test_existing_users_keep_their_data_and_get_safe_mrm_defaults(self):
        old_apps = self.migrate(self.before)
        User = old_apps.get_model('accounts', 'User')
        user = User.objects.create(username='veteran', email='vet@example.com', password='pbkdf2_sha256$1$s$h', role='STAFF')
        admin = User.objects.create(username='boss', email='boss@example.com', password='x', role='ADMIN', is_superuser=True)

        new_apps = self.migrate(self.after)
        User = new_apps.get_model('accounts', 'User')
        veteran, boss = User.objects.get(pk=user.pk), User.objects.get(pk=admin.pk)
        self.assertEqual((veteran.username, veteran.email, veteran.role, veteran.password), ('veteran', 'vet@example.com', 'STAFF', 'pbkdf2_sha256$1$s$h'))
        # nobody is silently granted MRM authority by the migration
        for u in (veteran, boss):
            self.assertEqual((u.mrm_authority, u.mrm_designation), ('', ''))
            self.assertFalse(u.signature)

    def test_migration_is_reversible_without_losing_accounts(self):
        self.migrate(self.after)
        from django.apps import apps
        apps.get_model('accounts', 'User').objects.create(username='keep', email='keep@example.com', password='x')
        old_apps = self.migrate(self.before)
        User = old_apps.get_model('accounts', 'User')
        self.assertTrue(User.objects.filter(username='keep').exists())
        self.assertFalse(hasattr(User, 'mrm_authority') and 'mrm_authority' in [f.name for f in User._meta.fields])
