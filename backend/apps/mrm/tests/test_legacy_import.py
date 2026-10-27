import hashlib
import json
import tempfile
import os
from datetime import datetime
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.mrm.legacy_import import DictSource, FlaskImporter, convert_password_hash
from apps.mrm.models import Hazard, MRMFeedback, MRMForm, SafetyOfficerAssignment
from apps.personnel.models import Personnel, Unit

from .test_mrm import MEDIA, png_signature


def werkzeug_pbkdf2(password, salt='abc123', iterations=1000):
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), iterations).hex()
    return f'pbkdf2:sha256:{iterations}${salt}${digest}'


def legacy_data():
    now = datetime(2026, 1, 5, 8, 0)
    return {
        'units': [
            {'id': 1, 'name': 'Tactical Operations Wing', 'acronym': 'TOW', 'category': 'Wing', 'parent_id': None, 'is_active': True},
            {'id': 2, 'name': '505th Squadron', 'acronym': '505S', 'category': 'Squadron', 'parent_id': 1, 'is_active': True},
        ],
        'users': [
            {'id': 1, 'username': 'adm', 'password_hash': werkzeug_pbkdf2('Legacy-pass-1'), 'authority': 'Administrator',
             'first_name': 'Ada', 'last_name': 'Min', 'unit_id': 1, 'designation': 'Commander', 'rank': 'COL', 'serial_number': 'A-1', 'is_active': True},
            {'id': 2, 'username': 'cre', 'password_hash': 'scrypt:32768:8:1$salt$deadbeef', 'authority': 'Creator',
             'email': 'cy@example.com', 'first_name': 'Cy', 'last_name': 'Creator', 'unit_id': 2, 'designation': 'Operator', 'rank': '1LT', 'serial_number': 'A-2',
             'signature_filename': 'cre.png', 'is_active': True},
            {'id': 3, 'username': 'eva', 'password_hash': werkzeug_pbkdf2('Legacy-pass-3'), 'authority': 'Evaluator',
             'first_name': 'Eve', 'last_name': 'Evaluator', 'unit_id': 2, 'designation': 'Supervisor', 'is_active': True},
            {'id': 4, 'username': 'uso', 'password_hash': werkzeug_pbkdf2('x'), 'authority': 'Unit Safety Officer',
             'first_name': 'Una', 'last_name': 'Safety', 'unit_id': 2, 'is_active': True},
        ],
        'unit_assignments': [{'id': 1, 'user_id': 4, 'unit_id': 1, 'is_primary': True}],
        'hazard_registry': [
            {'id': 10, 'unit': '505th Squadron', 'unit_id': 2, 'activity_code': 'Ground', 'hazard_description': 'Fuel spill',
             'before_likelihood': 4, 'before_severity': 'C', 'mitigations': 'Spill kit', 'after_likelihood': 4, 'after_severity': 'E', 'created_by': 3},
            {'id': 11, 'unit': '505th Squadron', 'unit_id': 2, 'activity_code': 'Air', 'hazard_description': 'Bad row',
             'before_likelihood': 9, 'before_severity': 'C', 'mitigations': 'm', 'after_likelihood': 1, 'after_severity': 'E', 'created_by': 3},
        ],
        'mrm_forms': [
            {'id': 100, 'mrm_number': '2025120101', 'activity_mission': 'Legacy approved', 'created_by': 2, 'reviewed_by': 3,
             'date_created': now, 'safety_objectives': 'Be safe', 'imsafes': json.dumps({'I': True, 'M': True, 'S': True, 'A': True, 'F': True, 'E': True}),
             'environment': 'Clear skies. Daylight.', 'mission_statement': 'Go', 'max_risk': 3, 'residual_risk': 1, 'total_percent': 33.3,
             'authority_level': 'Operator', 'status': 'reviewed', 'review_status': 'approved', 'date_reviewed': now, 'creator_signed': True,
             'evaluator_signed': True, 'authority_assigned_to': 2, 'authority_approved': True, 'authority_approval_date': now,
             'approved_pdf_filename': 'missing.pdf', 'original_unit_id': 2, 'edit_history': [{'who': 'cre'}]},
            {'id': 101, 'mrm_number': '2025120102', 'activity_mission': 'Legacy draft', 'created_by': 2, 'reviewed_by': 3, 'date_created': now,
             'safety_objectives': 'Draft obj', 'status': 'draft', 'review_status': 'pending', 'authority_level': 'Operator', 'original_unit_id': 2},
        ],
        'mission_hazards': [
            {'id': 1, 'mrm_id': 100, 'hazard_id': 10, 'selected': True},
            {'id': 2, 'mrm_id': 101, 'hazard_id': 10, 'selected': True},
            {'id': 3, 'mrm_id': 101, 'hazard_id': 10, 'selected': False},
        ],
        'mrm_personnel': [{'id': 1, 'mrm_id': 100, 'user_id': 3, 'role': 'Support', 'tagged_by': 2, 'is_active': True}],
        'mrm_feedback': [{'id': 1, 'mrm_id': 100, 'user_id': 3, 'risk_assessment_accuracy': 4, 'hazard_identification_rating': 5,
                          'mitigation_effectiveness': 9, 'what_went_well': 'Smooth', 'status': 'pending', 'submitted_at': now}],
        'feedback_notifications': [{'id': 1, 'feedback_id': 1, 'unit_safety_officer_id': 4, 'is_read': False}],
        'unit_logos': [],
    }


@override_settings(MEDIA_ROOT=MEDIA, PASSWORD_HASHERS=[
    'django.contrib.auth.hashers.PBKDF2PasswordHasher', 'django.contrib.auth.hashers.MD5PasswordHasher'])
class LegacyImportTests(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / 'cre.png').write_bytes(png_signature().read())

    def run_import(self, **kw):
        return FlaskImporter(DictSource(legacy_data()), signatures_dir=self.tmp, pdf_dir=self.tmp, **kw).run()

    def test_password_hash_conversion_is_lossless(self):
        user = User(username='x')
        user.password = convert_password_hash(werkzeug_pbkdf2('Legacy-pass-1'))
        self.assertTrue(user.check_password('Legacy-pass-1'))
        self.assertFalse(user.check_password('wrong'))
        self.assertIsNone(convert_password_hash('scrypt:32768:8:1$salt$deadbeef'))

    def test_full_import(self):
        report = self.run_import()
        self.assertEqual((report['units_created'], report['users_created'], report['forms']), (2, 4, 2))
        wing, sqn = Unit.objects.get(name='Tactical Operations Wing'), Unit.objects.get(name='505th Squadron')
        self.assertEqual(sqn.parent_unit_id, wing.id)
        self.assertEqual(wing.category, 'WING')

        adm, cre, uso = User.objects.get(username='adm'), User.objects.get(username='cre'), User.objects.get(username='uso')
        self.assertEqual(adm.role, User.Role.ADMIN)
        self.assertTrue(adm.check_password('Legacy-pass-1'))             # converted
        self.assertFalse(cre.has_usable_password())                      # scrypt can't be converted
        self.assertTrue(cre.must_change_password)
        self.assertEqual((cre.mrm_authority, cre.mrm_designation), ('CREATOR', 'OPERATOR'))
        self.assertTrue(cre.signature)
        self.assertEqual(report['passwords_converted'], 3)
        self.assertEqual(report['passwords_need_reset'], 1)

        self.assertEqual(Personnel.objects.get(linked_account=cre).rank.abbreviation, '1LT')
        self.assertEqual(cre.display_name_with_rank, '1LT Cy Creator')
        self.assertEqual(SafetyOfficerAssignment.objects.get(user=uso).unit_id, wing.id)

        self.assertEqual(Hazard.objects.count(), 1)                      # the invalid row was skipped
        self.assertTrue(any('Hazard #11' in w for w in report['warnings']))
        self.assertEqual(Hazard.objects.get().after_risk_rating, '4E')

        approved = MRMForm.objects.get(mrm_number='2025120101')
        self.assertTrue(approved.authority_approved)
        self.assertEqual(approved.unit_id, sqn.id)
        self.assertEqual(approved.created_at.year, 2026)
        self.assertEqual(approved.imsafe, {k: True for k in 'IMSAFE'})
        self.assertEqual(approved.mission_hazards.count(), 1)
        self.assertEqual(approved.tagged_personnel.get().role, 'Support')
        self.assertEqual(approved.events.first().metadata['legacy_edit_history'], [{'who': 'cre'}])
        self.assertEqual(report['files_missing'], ['approved PDF: missing.pdf'])

        # 4E is YELLOW on the official matrix (the legacy score formula called it low).
        # The approved form keeps its signed-off tier, but the discrepancy is reported.
        self.assertEqual(approved.authority_level, 'OPERATOR')
        self.assertEqual(report['risk_discrepancies'][0]['mrm_number'], '2025120101')
        self.assertEqual(report['risk_discrepancies'][0]['official_matrix_requires'], 'Squadron Commander')

        draft = MRMForm.objects.get(mrm_number='2025120102')
        self.assertEqual(draft.mission_hazards.count(), 1)               # deselected row not imported
        self.assertEqual(draft.total_percent, 66.7)                      # recomputed with the official matrix: 4E = medium
        self.assertEqual(draft.authority_level, 'SQUADRON_COMMANDER')

        fb = MRMFeedback.objects.get()
        self.assertEqual(fb.mitigation_effectiveness, 5)                 # clamped into 1-5
        self.assertEqual(fb.submitted_at.year, 2026)
        self.assertEqual(fb.notifications.count(), 1)

    def test_idempotent(self):
        self.run_import()
        counts = (User.objects.count(), Unit.objects.count(), Hazard.objects.count(), MRMForm.objects.count(), MRMFeedback.objects.count(),
                  Personnel.objects.count())
        second = self.run_import()
        self.assertEqual(counts, (User.objects.count(), Unit.objects.count(), Hazard.objects.count(), MRMForm.objects.count(),
                                  MRMFeedback.objects.count(), Personnel.objects.count()))
        self.assertEqual((second['users_created'], second['units_created']), (0, 0))

    def test_existing_uoms_accounts_are_not_overwritten(self):
        # same person: the email corroborates the match even though the usernames differ in case
        existing = User.objects.create_user(username='CRE', email='cy@example.com', password='Keep-my-pass-1', role=User.Role.VIEWER)
        self.run_import()
        existing.refresh_from_db()
        self.assertEqual(existing.role, User.Role.VIEWER)
        self.assertEqual(existing.email, 'cy@example.com')
        self.assertEqual(User.objects.filter(email='cy@example.com').count(), 1)   # no duplicate account
        self.assertTrue(existing.check_password('Keep-my-pass-1'))
        self.assertEqual(existing.mrm_authority, 'CREATOR')              # blank MRM fields are filled in
        self.assertIsNotNone(existing.unit_id)

    def test_dry_run_rolls_back(self):
        report = self.run_import(dry_run=True)
        self.assertEqual(report['forms'], 2)
        self.assertEqual((MRMForm.objects.count(), User.objects.count()), (0, 0))

    def test_json_dir_source_and_command(self):
        directory = Path(tempfile.mkdtemp())
        for table, rows in legacy_data().items():
            (directory / f'{table}.json').write_text(json.dumps(rows, default=str))
        call_command('import_flask_mrm', json_dir=str(directory), signatures_dir=str(self.tmp), stdout=open(os.devnull, 'w'))
        self.assertEqual(MRMForm.objects.count(), 2)


@override_settings(MEDIA_ROOT=MEDIA, PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class IdentityMatchingTests(TestCase):
    """Accounts are matched on reliable identifiers; names/usernames alone are never enough."""

    def run_import(self, **kw):
        return FlaskImporter(DictSource(legacy_data()), **kw).run()

    def test_same_username_different_person_is_not_merged(self):
        other = User.objects.create_user(username='cre', email='someone.else@example.com', password='x-Pass-12345', role=User.Role.VIEWER)
        report = self.run_import()
        self.assertEqual(User.objects.filter(username__iexact='cre').count(), 1)       # still just the existing account
        other.refresh_from_db()
        self.assertEqual(other.mrm_authority, '')                                       # untouched
        review = {r['legacy_username']: r for r in report['identity_review']}
        self.assertIn('cre', review)
        self.assertIn('emails differ', review['cre']['reason'])
        # forms made by the unresolved user were not imported (they would have been attributed to the wrong person)
        self.assertFalse(MRMForm.objects.filter(mrm_number='2025120101').exists())
        self.assertTrue(any('unresolved' in w for w in report['warnings']))

    def test_username_only_match_is_ambiguous_unless_trusted(self):
        User.objects.create_user(username='eva', email='eva@elsewhere.com', password='x-Pass-12345')
        rows = legacy_data()
        for u in rows['users']:
            u.pop('email', None)
        report = FlaskImporter(DictSource(rows)).run()
        self.assertIn('eva', {r['legacy_username'] for r in report['identity_review']})
        trusted = FlaskImporter(DictSource(rows), trust_usernames=True).run()
        self.assertNotIn('eva', {r['legacy_username'] for r in trusted['identity_review']})

    def test_service_number_links_to_the_existing_personnel_account(self):
        unit = Unit.objects.create(name='505th Squadron', code='505S', category='SQUADRON')
        from apps.personnel.models import Rank
        rank = Rank.objects.create(name='First Lieutenant', abbreviation='1LT', order=5)
        account = User.objects.create_user(username='cy.creator', email='cy.new@example.com', password='x-Pass-12345')
        Personnel.objects.create(service_number='A-2', first_name='Cy', last_name='Creator', rank=rank, unit=unit, linked_account=account)
        report = self.run_import()
        self.assertEqual(User.objects.filter(username__iexact='cre').count(), 0)        # mapped onto cy.creator, not duplicated
        account.refresh_from_db()
        self.assertEqual(account.mrm_authority, 'CREATOR')
        self.assertEqual(Personnel.objects.filter(service_number='A-2').count(), 1)
        self.assertNotIn('cre', {r['legacy_username'] for r in report['identity_review']})
        self.assertEqual(MRMForm.objects.get(mrm_number='2025120101').created_by_id, account.id)

    def test_conflicting_email_and_service_number_is_ambiguous(self):
        unit = Unit.objects.create(name='505th Squadron', code='505S', category='SQUADRON')
        from apps.personnel.models import Rank
        rank = Rank.objects.create(name='First Lieutenant', abbreviation='1LT', order=5)
        a = User.objects.create_user(username='a', email='cy@example.com', password='x-Pass-12345')
        b = User.objects.create_user(username='b', email='b@example.com', password='x-Pass-12345')
        Personnel.objects.create(service_number='A-2', first_name='X', last_name='Y', rank=rank, unit=unit, linked_account=b)
        report = self.run_import()
        item = next(r for r in report['identity_review'] if r['legacy_username'] == 'cre')
        self.assertIn('two different', item['reason'])
        self.assertEqual({c for c in item['candidates']}, {'a', 'b'})

    def test_human_decision_resolves_an_ambiguity(self):
        other = User.objects.create_user(username='cre', email='someone.else@example.com', password='x-Pass-12345')
        report = self.run_import(identity_map={'cre': 'cre'})            # an admin confirmed: same person
        self.assertEqual(report['identity_review'], [])
        self.assertEqual(MRMForm.objects.get(mrm_number='2025120101').created_by_id, other.id)
        self.assertEqual(User.objects.filter(username__iexact='cre').count(), 1)

    def test_marked_new_cannot_collide_with_an_existing_username(self):
        User.objects.create_user(username='cre', email='someone.else@example.com', password='x-Pass-12345')
        report = self.run_import(identity_map={'cre': 'NEW'})
        self.assertIn('already taken', report['identity_review'][0]['reason'])

    def test_placeholder_emails_are_reported(self):
        rows = legacy_data()
        report = FlaskImporter(DictSource(rows)).run()
        self.assertIn('adm', report['placeholder_emails'])
        self.assertNotIn('cre', report['placeholder_emails'])            # had a real email
