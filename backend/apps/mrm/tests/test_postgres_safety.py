"""
PostgreSQL enforces rules SQLite silently ignores (varchar length, strict UUID parsing, aborted transactions
after a DB error). These tests check those rules in Python so a violation fails on *any* database backend.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import override_settings

from apps.accounts.models import User
from apps.mrm.legacy_import import DictSource, FlaskImporter
from apps.mrm.models import (
    FeedbackNotification, Hazard, MissionHazard, MRMEvent, MRMFeedback, MRMForm, MRMPersonnel, UnitLogo,
)
from apps.personnel.models import Personnel, Rank

from .test_legacy_import import MEDIA, legacy_data
from .test_mrm import MRMTestCase, make_user


class VarcharLimitTests(MRMTestCase):
    def full_clean_all(self):
        """Run model validation (which enforces max_length) on every row the workflow produced."""
        for model in (Hazard, MRMForm, MissionHazard, MRMPersonnel, MRMFeedback, MRMEvent, FeedbackNotification, UnitLogo):
            for obj in model.objects.all():
                try:
                    obj.full_clean(exclude=['approved_pdf', 'image', 'legacy_id'])
                except DjangoValidationError as exc:
                    self.fail(f'{model.__name__} #{obj.pk} would violate a PostgreSQL column limit: {exc}')

    def test_every_object_in_a_full_workflow_fits_its_columns(self):
        form = self.create_form(tagged_personnel=[{'user': str(self.creator2.id), 'role': 'Crew Member'}],
                                hazards=[{'hazard': str(self.h_mid.id)}])
        self.advance_to_authority(form['id'])
        self.client_for(self.wing_cdr).post(f"/api/v1/mrm/forms/{form['id']}/approve/")
        self.client_for(self.creator2).post(f"/api/v1/mrm/forms/{form['id']}/feedback/", {'what_went_well': 'ok'}, format='json')
        self.full_clean_all()

    def test_worst_case_names_fit_the_snapshot_columns(self):
        rank = Rank.objects.create(name='R' * 100, abbreviation='A' * 20, order=1)
        creator = User.objects.create_user(
            username='x' * 150, email='long@example.com', password='Sup3r-Secret-pass',
            first_name='F' * 150, last_name='L' * 150, unit=self.sqn, mrm_authority='CREATOR',
        )
        Personnel.objects.create(service_number='S-LONG', first_name='F' * 100, last_name='L' * 100, rank=rank, unit=self.sqn, linked_account=creator)
        creator = User.objects.get(pk=creator.pk)
        self.assertGreater(len(creator.display_name_with_rank), 200)      # the old column size would have overflowed
        form = self.create_form(user=creator)
        self.client_for(creator).post(f"/api/v1/mrm/forms/{form['id']}/submit/")
        self.full_clean_all()
        self.assertLessEqual(len(MRMForm.objects.get(pk=form['id']).creator_name), 350)

    def test_long_values_from_the_api_are_rejected_or_trimmed_not_a_database_error(self):
        res = self.client_for(self.creator).post('/api/v1/mrm/forms/', self.payload(activity_mission='A' * 400, aircraft_vehicle='V' * 400), format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(len(res.data['activity_mission']), 255)
        self.full_clean_all()
        res = self.client_for(self.evaluator).post('/api/v1/mrm/hazards/', {
            'activity_code': 'C' * 300, 'hazard_description': 'd', 'mitigations': 'm',
            'before_likelihood': 3, 'before_severity': 'C', 'after_likelihood': 2, 'after_severity': 'D'}, format='json')
        self.assertEqual(res.status_code, 400)                              # serializer enforces max_length=100

    def test_personnel_role_is_trimmed_to_its_column(self):
        res = self.client_for(self.creator).post('/api/v1/mrm/forms/', self.payload(
            tagged_personnel=[{'user': str(self.creator2.id), 'role': 'R' * 500}]), format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(len(res.data['tagged_personnel'][0]['role']), 100)


@override_settings(MEDIA_ROOT=MEDIA)
class ImporterVarcharTests(MRMTestCase):
    def test_import_with_overlong_legacy_values_never_exceeds_a_column(self):
        rows = legacy_data()
        rows['users'][1].update(first_name='F' * 150, last_name='L' * 150, rank='1LT-' + 'X' * 40, contact_number='0' * 80)
        rows['hazard_registry'][0]['activity_code'] = 'A' * 300
        rows['mrm_forms'][0]['activity_mission'] = 'M' * 400
        rows['mrm_forms'].append({**rows['mrm_forms'][1], 'id': 102, 'mrm_number': '9' * 25})
        report = FlaskImporter(DictSource(rows)).run()
        self.assertTrue(any('longer than 20' in w for w in report['warnings']))
        for model in (Personnel, Rank, Hazard, MRMForm):
            for obj in model.objects.all():
                try:
                    obj.full_clean(exclude=['approved_pdf', 'image', 'legacy_id', 'photo'])
                except DjangoValidationError as exc:
                    self.fail(f'imported {model.__name__} violates a column limit: {exc}')


class StrictInputTests(MRMTestCase):
    def test_malformed_uuids_return_400_not_500(self):
        c = self.client_for(self.admin)
        for url in ('/api/v1/mrm/forms/?unit=not-a-uuid', '/api/v1/mrm/forms/?mission=oops', '/api/v1/mrm/hazards/?unit=nope',
                    '/api/v1/mrm/forms/evaluators/?unit=nope', '/api/v1/mrm/analytics/?unit=nope'):
            res = c.get(url)
            self.assertIn(res.status_code, (400, 403), url)
        self.assertEqual(c.get('/api/v1/mrm/forms/not-a-uuid/').status_code, 404)
        self.assertEqual(c.post('/api/v1/mrm/forms/', self.payload(reviewer='nope', unit=str(self.sqn.id)), format='json').status_code, 400)
        self.assertEqual(c.post('/api/v1/mrm/hazards/bulk-delete/', {'ids': ['nope']}, format='json').status_code, 400)

    def test_a_caught_database_error_does_not_poison_the_approval_transaction(self):
        """PostgreSQL aborts the whole transaction after any DB error — approval must survive a failing PDF step."""
        from unittest import mock
        form = self.create_form()
        self.advance_to_authority(form['id'])
        with mock.patch('apps.mrm.pdf.generate_pdf', side_effect=RuntimeError('boom')):
            res = self.client_for(self.creator).post(f"/api/v1/mrm/forms/{form['id']}/approve/")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(res.data['authority_approved'])
        self.assertTrue(res.data['warnings'])
        self.assertFalse(res.data['has_pdf'])
        self.client_for(self.admin).post(f"/api/v1/mrm/forms/{form['id']}/regenerate-pdf/")
        self.assertTrue(MRMForm.objects.get(pk=form['id']).approved_pdf)
