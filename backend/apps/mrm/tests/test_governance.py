from django.core.management import call_command
from django.test import override_settings
from io import StringIO

from apps.accounts.models import User
from apps.core.models import AuditLog
from apps.missions.models import HazardAssessment, Mission

from .test_mrm import A, D, MRMTestCase, make_user


class AuditAndDeactivationTests(MRMTestCase):
    def test_security_attribute_changes_are_audited_with_before_and_after(self):
        c = self.client_for(self.admin)
        res = c.patch(f'/api/v1/auth/users/{self.creator2.id}/', {'role': 'STAFF', 'mrm_authority': A.EVALUATOR, 'mrm_designation': D.SUPERVISOR}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        entry = AuditLog.objects.filter(object_id=str(self.creator2.id), action='UPDATE').latest('id')
        changes = entry.metadata['security_changes']
        self.assertEqual(changes['role'], {'from': 'VIEWER', 'to': 'STAFF'})
        self.assertEqual(changes['mrm_authority'], {'from': 'CREATOR', 'to': 'EVALUATOR'})
        self.assertEqual(changes['mrm_designation']['to'], 'SUPERVISOR')
        self.assertNotIn('unit_id', changes)                              # unchanged fields are not logged
        self.assertEqual(entry.user_id, self.admin.id)

    def test_non_security_edit_is_logged_without_security_changes(self):
        self.client_for(self.admin).patch(f'/api/v1/auth/users/{self.creator2.id}/', {'phone_number': '0917'}, format='json')
        entry = AuditLog.objects.filter(object_id=str(self.creator2.id), action='UPDATE').latest('id')
        self.assertEqual(entry.metadata, {})

    def test_creating_a_user_records_the_granted_attributes(self):
        res = self.client_for(self.admin).post('/api/v1/auth/users/', {
            'username': 'newbie', 'email': 'newbie@example.com', 'password': 'Sup3r-Secret-pass', 'role': 'OPERATOR',
            'mrm_authority': A.CREATOR, 'first_name': 'N', 'last_name': 'B'}, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        entry = AuditLog.objects.filter(action='CREATE', model_name='User').latest('id')
        self.assertEqual(entry.metadata['security_attributes']['mrm_authority'], 'CREATOR')

    def _submit_for_review(self):
        form = self.create_form()
        self.client_for(self.creator).post(f"/api/v1/mrm/forms/{form['id']}/submit/")
        return form

    def test_cannot_deactivate_a_user_with_pending_mrm_work(self):
        form = self._submit_for_review()
        c = self.client_for(self.admin)
        res = c.patch(f'/api/v1/auth/users/{self.evaluator.id}/', {'is_active': False}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn(form['mrm_number'], str(res.data))
        self.assertEqual(c.delete(f'/api/v1/auth/users/{self.evaluator.id}/').status_code, 400)
        self.evaluator.refresh_from_db()
        self.assertTrue(self.evaluator.is_active)
        # the Safety Office path obeys the same policy
        self.assertEqual(self.client_for(self.uso).post(f'/api/v1/mrm/safety/users/{self.evaluator.id}/toggle-active/').status_code, 400)

    def test_reassigning_the_reviewer_unblocks_deactivation(self):
        form = self._submit_for_review()
        spare = make_user('spare', self.sqn, authority=A.EVALUATOR)
        # creators cannot reassign; admins and in-scope safety officers can
        self.assertEqual(self.client_for(self.creator).post(f"/api/v1/mrm/forms/{form['id']}/reassign-reviewer/", {'reviewer': str(spare.id)}, format='json').status_code, 403)
        self.assertEqual(self.client_for(self.outsider_uso).post(f"/api/v1/mrm/forms/{form['id']}/reassign-reviewer/", {'reviewer': str(spare.id)}, format='json').status_code, 404)
        res = self.client_for(self.uso).post(f"/api/v1/mrm/forms/{form['id']}/reassign-reviewer/", {'reviewer': str(spare.id)}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['reviewer']['username'], 'spare')
        ok = self.client_for(self.admin).patch(f'/api/v1/auth/users/{self.evaluator.id}/', {'is_active': False}, format='json')
        self.assertEqual(ok.status_code, 200, ok.data)
        # the new reviewer can act; the old one no longer can
        self.assertEqual(self.client_for(spare).post(f"/api/v1/mrm/forms/{form['id']}/review/", {'review_status': 'approved'}, format='json').status_code, 200)

    def test_reviewer_cannot_be_reassigned_once_review_happened_or_to_the_creator(self):
        form = self._submit_for_review()
        bad = self.client_for(self.admin).post(f"/api/v1/mrm/forms/{form['id']}/reassign-reviewer/", {'reviewer': str(self.creator.id)}, format='json')
        self.assertEqual(bad.status_code, 400)
        self.client_for(self.evaluator).post(f"/api/v1/mrm/forms/{form['id']}/review/", {'review_status': 'approved'}, format='json')
        spare = make_user('spare', self.sqn, authority=A.EVALUATOR)
        late = self.client_for(self.admin).post(f"/api/v1/mrm/forms/{form['id']}/reassign-reviewer/", {'reviewer': str(spare.id)}, format='json')
        self.assertEqual(late.status_code, 400)

    def test_pending_approval_also_blocks_deactivation(self):
        form = self.create_form()
        self.advance_to_authority(form['id'])                              # creator is the Operator-tier approver
        res = self.client_for(self.admin).patch(f'/api/v1/auth/users/{self.creator.id}/', {'is_active': False}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('approval', str(res.data))

    def test_admin_cannot_deactivate_themselves(self):
        res = self.client_for(self.admin).patch(f'/api/v1/auth/users/{self.admin.id}/', {'is_active': False}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_users_without_pending_work_deactivate_normally_and_are_audited(self):
        res = self.client_for(self.admin).patch(f'/api/v1/auth/users/{self.creator2.id}/', {'is_active': False}, format='json')
        self.assertEqual(res.status_code, 200)
        entry = AuditLog.objects.filter(object_id=str(self.creator2.id), action='UPDATE').latest('id')
        self.assertEqual(entry.metadata['security_changes']['is_active'], {'from': 'True', 'to': 'False'})


class SingleSourceOfTruthTests(MRMTestCase):
    def setUp(self):
        self.mission = Mission.objects.create(name='Operation X', unit=self.sqn)

    def test_legacy_hazard_assessments_are_frozen_once_the_mission_has_an_mrm(self):
        legacy = HazardAssessment.objects.create(mission=self.mission, hazard_description='old', category='OTHER',
                                                 probability='OCCASIONAL', severity='MODERATE')
        c = self.client_for(self.admin)
        body = {'hazard_description': 'x', 'category': 'OTHER', 'probability': 'OCCASIONAL', 'severity': 'MODERATE'}
        # before an MRM exists the old path still works (default configuration)
        self.assertEqual(c.patch(f'/api/v1/missions/hazards/{legacy.id}/', {'hazard_description': 'edited'}, format='json').status_code, 200)
        self.create_form(mission=str(self.mission.id))
        for res in (
            c.post(f'/api/v1/missions/profiles/{self.mission.id}/hazards/', body, format='json'),
            c.patch(f'/api/v1/missions/hazards/{legacy.id}/', {'hazard_description': 'again'}, format='json'),
            c.delete(f'/api/v1/missions/hazards/{legacy.id}/'),
        ):
            self.assertEqual(res.status_code, 400, res.data)
            self.assertIn('MRM', str(res.data))
        legacy.refresh_from_db()
        self.assertEqual(legacy.hazard_description, 'edited')            # untouched, still readable
        self.assertEqual(c.get(f'/api/v1/missions/profiles/{self.mission.id}/hazards/').status_code, 200)

    def test_enforcement_freezes_hazard_writes_for_every_mission(self):
        with override_settings(MRM_REQUIRE_FOR_MISSION_APPROVAL=True):
            res = self.client_for(self.admin).post(f'/api/v1/missions/profiles/{self.mission.id}/hazards/', {}, format='json')
            self.assertEqual(res.status_code, 400)

    def test_mission_review_status_is_a_projection_of_the_mrm_and_cannot_be_edited_directly(self):
        form = self.create_form(mission=str(self.mission.id))
        self.client_for(self.creator).post(f"/api/v1/mrm/forms/{form['id']}/submit/")
        res = self.client_for(self.admin).patch(f'/api/v1/missions/profiles/{self.mission.id}/', {'risk_review_status': 'APPROVED'}, format='json')
        self.assertEqual(res.status_code, 200)
        self.mission.refresh_from_db()
        self.assertEqual(self.mission.risk_review_status, 'SUBMITTED')   # the API ignored the write

    def test_consistency_command_detects_and_fixes_drift(self):
        form = self.create_form(mission=str(self.mission.id))
        self.client_for(self.creator).post(f"/api/v1/mrm/forms/{form['id']}/submit/")
        Mission.objects.filter(pk=self.mission.pk).update(risk_review_status='APPROVED')   # simulate a stray direct write
        out = StringIO()
        call_command('check_mrm_consistency', stdout=out)
        self.assertIn('drifted', out.getvalue())
        call_command('check_mrm_consistency', '--fix', stdout=StringIO())
        self.mission.refresh_from_db()
        self.assertEqual(self.mission.risk_review_status, 'SUBMITTED')
        out = StringIO()
        call_command('check_mrm_consistency', stdout=out)
        self.assertIn('No drift', out.getvalue())


class ReportsReadTheMrmTests(MRMTestCase):
    def setUp(self):
        self.mission = Mission.objects.create(name='Operation Y', unit=self.sqn)

    def test_risk_report_lists_mrm_hazards_and_hides_superseded_legacy_rows(self):
        from apps.reports.services import risk_report
        HazardAssessment.objects.create(mission=self.mission, hazard_description='legacy only', category='OTHER',
                                        probability='OCCASIONAL', severity='MODERATE')
        other = Mission.objects.create(name='No MRM here', unit=self.sqn)
        HazardAssessment.objects.create(mission=other, hazard_description='legacy kept', category='OTHER',
                                        probability='LIKELY', severity='CRITICAL')
        self.create_form(mission=str(self.mission.id), hazards=[{'hazard': str(self.h_high.id)}, {'hazard': str(self.h_low.id)}])
        _, headers, rows = risk_report()
        text = ' | '.join(' '.join(map(str, r)) for r in rows)
        self.assertIn('Engine failure', text)                          # MRM hazard present
        self.assertIn('High (5A)', text)                               # initial rating from the official matrix
        self.assertIn('High (4A)', text)                               # residual
        self.assertNotIn('legacy only', text)                          # superseded by the MRM
        self.assertIn('legacy kept', text)                             # mission without an MRM is still reported
        self.assertEqual(headers[0], 'Source')

    def test_mission_report_uses_the_mrm_status_not_the_projection(self):
        from apps.reports.services import mission_report
        form = self.create_form(mission=str(self.mission.id))
        self.client_for(self.creator).post(f"/api/v1/mrm/forms/{form['id']}/submit/")
        Mission.objects.filter(pk=self.mission.pk).update(risk_review_status='DRAFT')   # stale projection
        rows = {r[0]: r for r in mission_report()[2]}
        self.assertEqual(rows['Operation Y'][3], 'Submitted for Approval')

    def test_admin_mission_form_is_read_only_for_projected_fields(self):
        from django.contrib import admin as dj_admin
        from apps.missions.admin import MissionAdmin
        ma = MissionAdmin(Mission, dj_admin.site)
        self.assertIn('risk_review_status', ma.readonly_fields)
        self.assertIn('review_comments', ma.readonly_fields)
