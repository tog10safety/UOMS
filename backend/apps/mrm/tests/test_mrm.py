import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.core.models import RolePermission
from apps.core.rbac import Action, Module
from apps.missions.models import Mission
from apps.mrm import risk
from apps.mrm.models import Hazard, MRMForm
from apps.personnel.models import Unit

MEDIA = tempfile.mkdtemp(prefix='mrm_test_media_')
A = User.MRMAuthority
D = User.MRMDesignation

ENV = {'weather': 'Clear skies', 'lighting': 'Daylight', 'workspace': 'Clean and organized',
       'operational_tempo': 'Normal / Routine operations'}
IMSAFE = {k: True for k in 'IMSAFE'}


def png_signature(name='sig.png'):
    buf = io.BytesIO()
    Image.new('RGB', (120, 40), 'white').save(buf, 'PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


def make_user(username, unit=None, role=User.Role.VIEWER, authority='', designation='', signed=False, **kw):
    user = User.objects.create_user(
        username=username, email=f'{username}@example.com', password='Sup3r-Secret-pass', role=role, unit=unit,
        mrm_authority=authority, mrm_designation=designation, first_name=username.title(), last_name='Tester', **kw,
    )
    if signed:
        user.signature.save(f'{username}.png', png_signature(), save=True)
    return user


@override_settings(MEDIA_ROOT=MEDIA)
class MRMTestCase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        # every UOMS role can view the module (matches the default RBAC matrix)
        for role in ('COMMANDER', 'STAFF', 'OPERATOR', 'VIEWER'):
            RolePermission.objects.create(role=role, module=Module.MISSIONS, action=Action.VIEW, is_granted=True)

        cls.wing = Unit.objects.create(name='1st Wing', code='1W', category=Unit.Category.WING)
        cls.sqn = Unit.objects.create(name='101st Squadron', code='101S', category=Unit.Category.SQUADRON, parent_unit=cls.wing)
        cls.other_sqn = Unit.objects.create(name='102nd Squadron', code='102S', category=Unit.Category.SQUADRON, parent_unit=cls.wing)

        cls.admin = make_user('admin', role=User.Role.ADMIN, signed=True)
        cls.creator = make_user('creator', cls.sqn, authority=A.CREATOR, signed=True)
        cls.creator2 = make_user('creator2', cls.sqn, authority=A.CREATOR)
        cls.evaluator = make_user('evaluator', cls.sqn, authority=A.EVALUATOR, designation=D.SUPERVISOR, signed=True)
        cls.wing_cdr = make_user('wingcdr', cls.wing, authority=A.CREATOR, designation=D.SQUADRON_COMMANDER, signed=True)
        cls.uso = make_user('uso', cls.sqn, authority=A.UNIT_SAFETY_OFFICER)
        cls.outsider_uso = make_user('uso2', cls.other_sqn, authority=A.UNIT_SAFETY_OFFICER)
        cls.other_creator = make_user('other', cls.other_sqn, authority=A.CREATOR)
        cls.no_authority = make_user('nobody', cls.sqn)

        def hz(code, desc, bl, bs, al, a_s, unit=None):
            return Hazard.objects.create(unit=unit or cls.sqn, activity_code=code, hazard_description=desc, before_likelihood=bl,
                                         before_severity=bs, mitigations='Brief crew\nCheck equipment', after_likelihood=al,
                                         after_severity=a_s, created_by=cls.evaluator)
        cls.h_low = hz('Ground', 'Slip on wet ramp', 3, 'C', 1, 'E')       # residual 1E -> LOW
        cls.h_mid = hz('Ground', 'Vehicle rollover', 4, 'B', 3, 'C')        # residual 3C -> MEDIUM
        cls.h_high = hz('Air', 'Engine failure', 5, 'A', 4, 'A')            # residual 4A -> HIGH
        cls.h_mother = hz('Air', 'Wing-level FOD hazard', 3, 'B', 2, 'D', unit=cls.wing)
        cls.h_mid2 = hz('Ground', 'Fuel spill', 4, 'C', 4, 'C')             # residual 4C -> MEDIUM

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def payload(self, hazards=None, **extra):
        data = {
            'activity_mission': 'Resupply sortie', 'safety_objectives': 'Deliver cargo safely.',
            'reviewer': str(self.evaluator.id), 'imsafe': IMSAFE, 'environment': ENV, 'aircraft_vehicle': 'UH-1H',
            'hazards': [{'hazard': str(self.h_low.id)}] if hazards is None else hazards,
        }
        data.update(extra)
        return data

    def create_form(self, user=None, **kw):
        res = self.client_for(user or self.creator).post('/api/v1/mrm/forms/', self.payload(**kw), format='json')
        self.assertEqual(res.status_code, 201, res.data)
        return res.data

    def advance_to_authority(self, form_id):
        c = self.client_for(self.creator)
        self.assertEqual(c.post(f'/api/v1/mrm/forms/{form_id}/submit/').status_code, 200)
        res = self.client_for(self.evaluator).post(f'/api/v1/mrm/forms/{form_id}/review/', {'review_status': 'approved'}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        return res.data


class RiskEngineTests(TestCase):
    def test_official_matrix_covers_all_25_cells_once(self):
        cells = {f'{l}{s}' for l in range(1, 6) for s in 'ABCDE'}
        self.assertEqual(risk.RED | risk.YELLOW | risk.GREEN, cells)
        self.assertFalse(risk.RED & risk.YELLOW or risk.YELLOW & risk.GREEN or risk.RED & risk.GREEN)

    def test_cells_the_legacy_score_formula_got_wrong(self):
        for cell in ('5E', '4E', '1A'):  # raw score <6 made these 'low' in the old app; the official matrix says medium
            self.assertEqual(risk.level(cell), risk.MEDIUM)

    def test_tiers(self):
        self.assertEqual(risk.summarize([(5, 'A')]).authority_level, 'COMMANDER')
        self.assertEqual(risk.summarize([(1, 'E')]).authority_level, 'OPERATOR')
        self.assertEqual(risk.summarize([(3, 'C')]).authority_level, 'SQUADRON_COMMANDER')   # 66.7%
        self.assertEqual(risk.summarize([(3, 'C'), (3, 'C'), (1, 'E')]).authority_level, 'SUPERVISOR')  # 55.6%
        self.assertEqual(risk.summarize([(3, 'C'), (3, 'C'), (4, 'A')]).authority_level, 'DIRECTOR_FOR_OPERATIONS')  # 77.8%
        self.assertEqual(risk.summarize([(4, 'A'), (4, 'A'), (3, 'C')]).authority_level, 'COMMANDER')  # 88.9%

    def test_bad_input(self):
        with self.assertRaises(risk.RiskInputError):
            risk.rating(6, 'A')
        with self.assertRaises(risk.RiskInputError):
            risk.rating(3, 'Z')


class HazardRegistryTests(MRMTestCase):
    def test_creator_is_read_only_evaluator_can_write(self):
        body = {'activity_code': 'Ground', 'hazard_description': 'New hazard', 'mitigations': 'Mitigate',
                'before_likelihood': 4, 'before_severity': 'B', 'after_likelihood': 2, 'after_severity': 'C'}
        self.assertEqual(self.client_for(self.creator).post('/api/v1/mrm/hazards/', body, format='json').status_code, 403)
        res = self.client_for(self.evaluator).post('/api/v1/mrm/hazards/', body, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['before_risk_rating'], '4B')
        self.assertEqual(res.data['after_level'], 'MEDIUM')
        self.assertEqual(str(res.data['unit']), str(self.sqn.id))

    def test_hazard_cannot_be_moved_to_another_unit(self):
        res = self.client_for(self.evaluator).patch(
            f'/api/v1/mrm/hazards/{self.h_low.id}/', {'unit': str(self.other_sqn.id), 'mitigations': 'Updated'}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.h_low.refresh_from_db()
        self.assertEqual(self.h_low.unit_id, self.sqn.id)
        self.assertEqual(self.h_low.mitigations, 'Updated')

    def test_invalid_ratings_rejected(self):
        res = self.client_for(self.evaluator).post('/api/v1/mrm/hazards/', {
            'activity_code': 'x', 'hazard_description': 'y', 'mitigations': 'z',
            'before_likelihood': 9, 'before_severity': 'B', 'after_likelihood': 2, 'after_severity': 'C'}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_unit_scoping_and_cross_unit_write_blocked(self):
        other = Hazard.objects.create(unit=self.other_sqn, activity_code='X', hazard_description='Not yours', before_likelihood=3,
                                      before_severity='C', mitigations='m', after_likelihood=2, after_severity='D')
        res = self.client_for(self.evaluator).get('/api/v1/mrm/hazards/')
        ids = {h['id'] for h in res.data['results']}
        self.assertNotIn(str(other.id), ids)
        self.assertIn(str(self.h_low.id), ids)
        # the legacy app let any evaluator edit/delete other units' hazards by id — now a 404 (not visible)
        self.assertEqual(self.client_for(self.evaluator).delete(f'/api/v1/mrm/hazards/{other.id}/').status_code, 404)
        bulk = self.client_for(self.evaluator).post('/api/v1/mrm/hazards/bulk-delete/', {'ids': [str(other.id)]}, format='json')
        self.assertEqual(bulk.data['deleted'], 0)
        other.refresh_from_db()
        self.assertTrue(other.is_active)

    def test_cannot_delete_hazard_in_use(self):
        self.create_form()
        res = self.client_for(self.evaluator).delete(f'/api/v1/mrm/hazards/{self.h_low.id}/')
        self.assertEqual(res.status_code, 400)

    def test_risk_level_filter(self):
        res = self.client_for(self.evaluator).get('/api/v1/mrm/hazards/?risk_level=high')
        self.assertEqual([h['id'] for h in res.data['results']], [str(self.h_high.id)])

    def test_pickable_includes_mother_unit_hazards(self):
        res = self.client_for(self.creator).get('/api/v1/mrm/hazards/pickable/')
        self.assertIn(str(self.h_mother.id), {h['id'] for h in res.data['results']})

    def test_excel_roundtrip(self):
        c = self.client_for(self.evaluator)
        exported = c.get('/api/v1/mrm/hazards/export/')
        self.assertEqual(exported.status_code, 200)
        template = c.get('/api/v1/mrm/hazards/import-template/')
        upload = SimpleUploadedFile('h.xlsx', template.content, content_type='application/octet-stream')
        res = c.post('/api/v1/mrm/hazards/import/', {'file': upload}, format='multipart')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['created'], 1)
        again = c.post('/api/v1/mrm/hazards/import/', {'file': SimpleUploadedFile('h.xlsx', template.content)}, format='multipart')
        self.assertEqual(again.data['created'], 0)
        self.assertEqual(again.data['skipped'], 1)


class FormCreationTests(MRMTestCase):
    def test_create_computes_risk(self):
        form = self.create_form(hazards=[{'hazard': str(self.h_mid.id)}, {'hazard': str(self.h_low.id)}])
        self.assertEqual(form['risk']['total_percent'], 50.0)
        self.assertEqual(form['risk']['authority_level'], 'OPERATOR')
        self.assertTrue(form['mrm_number'].isdigit())
        self.assertEqual(form['stage'], 'draft')

    def test_numbers_are_unique_and_sequential(self):
        a, b = self.create_form(), self.create_form()
        self.assertEqual(int(b['mrm_number']), int(a['mrm_number']) + 1)

    def test_validation(self):
        c = self.client_for(self.creator)
        for bad in ({'hazards': []}, {'imsafe': {'I': True}}, {'environment': {'weather': 'Clear skies'}},
                    {'environment': {**ENV, 'weather': 'Raining frogs'}}, {'reviewer': ''},
                    {'reviewer': str(self.creator.id)},   # self-review
                    {'hazards': [{'hazard': str(self.h_low.id), 'override_likelihood': 3}]}):
            res = c.post('/api/v1/mrm/forms/', self.payload(**bad), format='json')
            self.assertEqual(res.status_code, 400, bad)

    def test_override_requires_justification(self):
        item = {'hazard': str(self.h_high.id), 'override_likelihood': 1, 'override_severity': 'E'}
        res = self.client_for(self.creator).post('/api/v1/mrm/forms/', self.payload(hazards=[item]), format='json')
        self.assertEqual(res.status_code, 400)
        item['additional_mitigations'] = 'Aircraft grounded; mission cancelled for this hazard'
        res = self.client_for(self.creator).post('/api/v1/mrm/forms/', self.payload(hazards=[item]), format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['risk']['total_percent'], 33.3)

    def test_cannot_use_other_units_hazards(self):
        foreign = Hazard.objects.create(unit=self.other_sqn, activity_code='X', hazard_description='Foreign', before_likelihood=3,
                                        before_severity='C', mitigations='m', after_likelihood=2, after_severity='D')
        res = self.client_for(self.creator).post('/api/v1/mrm/forms/', self.payload(hazards=[{'hazard': str(foreign.id)}]), format='json')
        self.assertEqual(res.status_code, 400)

    def test_users_without_creator_authority_cannot_create(self):
        for user in (self.no_authority, self.uso):
            self.assertEqual(self.client_for(user).post('/api/v1/mrm/forms/', self.payload(), format='json').status_code, 403)

    def test_live_risk_preview(self):
        res = self.client_for(self.creator).post('/api/v1/mrm/forms/calculate-risk/',
                                                 {'hazards': [{'hazard': str(self.h_high.id)}]}, format='json')
        self.assertEqual(res.data['authority_level'], 'COMMANDER')
        self.assertEqual(res.data['total_percent'], 100.0)

    def test_evaluator_candidates_exclude_self(self):
        res = self.client_for(self.evaluator).get('/api/v1/mrm/forms/evaluators/')
        self.assertEqual(res.data, [])
        res = self.client_for(self.creator).get('/api/v1/mrm/forms/evaluators/')
        self.assertEqual([e['id'] for e in res.data], [str(self.evaluator.id)])

    def test_tagging_must_be_same_unit(self):
        res = self.client_for(self.creator).post('/api/v1/mrm/forms/', self.payload(
            tagged_personnel=[{'user': str(self.other_creator.id), 'role': 'Crew Member'}]), format='json')
        self.assertEqual(res.status_code, 400)
        res = self.client_for(self.creator).post('/api/v1/mrm/forms/', self.payload(
            tagged_personnel=[{'user': str(self.creator2.id), 'role': 'Crew Member'}]), format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(len(res.data['tagged_personnel']), 1)


class WorkflowTests(MRMTestCase):
    def test_full_operator_tier_workflow(self):
        form = self.create_form()   # 1E residual => Operator => creator approves
        fid = form['id']
        res = self.client_for(self.creator).post(f'/api/v1/mrm/forms/{fid}/submit/')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['stage'], 'awaiting_review')
        self.assertTrue(res.data['creator_signed'])

        review = self.client_for(self.evaluator).post(f'/api/v1/mrm/forms/{fid}/review/', {'review_status': 'approved'}, format='json')
        self.assertEqual(review.status_code, 200, review.data)
        self.assertEqual(review.data['stage'], 'awaiting_authority')
        self.assertEqual(review.data['authority']['username'], 'creator')
        self.assertTrue(review.data['evaluator_signed'])

        # only the assigned authority may approve
        self.assertEqual(self.client_for(self.evaluator).post(f'/api/v1/mrm/forms/{fid}/approve/').status_code, 403)
        done = self.client_for(self.creator).post(f'/api/v1/mrm/forms/{fid}/approve/', {'comments': 'Go'}, format='json')
        self.assertEqual(done.status_code, 200, done.data)
        self.assertEqual(done.data['stage'], 'approved')
        self.assertTrue(done.data['has_pdf'])
        self.assertEqual(done.data['warnings'], [])

        # locked afterwards
        edit = self.client_for(self.admin).patch(f'/api/v1/mrm/forms/{fid}/', {'activity_mission': 'Changed'}, format='json')
        self.assertEqual(edit.status_code, 403)
        pdf = self.client_for(self.creator).get(f'/api/v1/mrm/forms/{fid}/pdf/')
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(b''.join(pdf.streaming_content)[:4], b'%PDF')

    def test_supervisor_tier_routes_to_the_reviewing_evaluator(self):
        form = self.create_form(hazards=[{'hazard': str(h.id)} for h in (self.h_mid, self.h_mid2, self.h_low)])
        self.assertEqual(form['risk']['total_percent'], 55.6)
        self.assertEqual(form['risk']['authority_level'], 'SUPERVISOR')
        res = self.advance_to_authority(form['id'])
        self.assertEqual(res['authority']['username'], 'evaluator')

    def test_higher_tier_finds_designation_in_mother_unit_and_never_the_creator(self):
        # 3C alone = 66.7% -> Squadron Commander; the only holder is in the parent Wing
        form = self.create_form(hazards=[{'hazard': str(self.h_mid.id)}])
        self.assertEqual(form['risk']['authority_level'], 'SQUADRON_COMMANDER')
        res = self.advance_to_authority(form['id'])
        self.assertEqual(res['authority']['username'], 'wingcdr')
        self.assertEqual(res['stage'], 'awaiting_authority')

        done = self.client_for(self.wing_cdr).post(f"/api/v1/mrm/forms/{form['id']}/approve/")
        self.assertEqual(done.status_code, 200, done.data)
        self.assertTrue(done.data['authority_approved'])

    def test_creator_holding_the_designation_is_skipped(self):
        self.creator.mrm_designation = D.SQUADRON_COMMANDER
        self.creator.save()
        form = self.create_form(hazards=[{'hazard': str(self.h_mid.id)}])
        res = self.advance_to_authority(form['id'])
        self.assertEqual(res['authority']['username'], 'wingcdr')  # not the creator

    def test_unfilled_designation_needs_manual_assignment(self):
        self.wing_cdr.mrm_designation = ''
        self.wing_cdr.save()
        form = self.create_form(hazards=[{'hazard': str(self.h_mid.id)}])
        res = self.advance_to_authority(form['id'])
        self.assertEqual(res['stage'], 'needs_authority_assignment')
        self.assertTrue(res['warnings'])
        # a USO in scope can fix it once somebody holds the designation
        self.wing_cdr.mrm_designation = D.SQUADRON_COMMANDER
        self.wing_cdr.save()
        fixed = self.client_for(self.uso).post(f"/api/v1/mrm/forms/{form['id']}/reassign-authority/", {}, format='json')
        self.assertEqual(fixed.status_code, 200, fixed.data)
        self.assertEqual(fixed.data['authority']['username'], 'wingcdr')
        # a creator cannot
        self.assertEqual(self.client_for(self.creator).post(f"/api/v1/mrm/forms/{form['id']}/reassign-authority/", {}, format='json').status_code, 403)

    def test_authority_must_have_a_signature(self):
        form = self.create_form()
        self.advance_to_authority(form['id'])
        self.creator.signature.delete(save=True)
        res = self.client_for(self.creator).post(f"/api/v1/mrm/forms/{form['id']}/approve/")
        self.assertEqual(res.status_code, 400)

    def test_review_rules(self):
        form = self.create_form()
        fid = form['id']
        # cannot review a draft
        self.assertEqual(self.client_for(self.evaluator).post(f'/api/v1/mrm/forms/{fid}/review/', {'review_status': 'approved'}, format='json').status_code, 403)
        self.client_for(self.creator).post(f'/api/v1/mrm/forms/{fid}/submit/')
        # wrong evaluator / creator cannot review
        stranger = make_user('eval2', self.sqn, authority=A.EVALUATOR)
        self.assertEqual(self.client_for(stranger).post(f'/api/v1/mrm/forms/{fid}/review/', {'review_status': 'approved'}, format='json').status_code, 404)
        self.assertEqual(self.client_for(self.creator).post(f'/api/v1/mrm/forms/{fid}/review/', {'review_status': 'approved'}, format='json').status_code, 403)
        # rejection needs a reason
        self.assertEqual(self.client_for(self.evaluator).post(f'/api/v1/mrm/forms/{fid}/review/', {'review_status': 'rejected'}, format='json').status_code, 400)

    def test_rejected_form_can_be_revised_and_resubmitted(self):
        form = self.create_form()
        fid = form['id']
        self.client_for(self.creator).post(f'/api/v1/mrm/forms/{fid}/submit/')
        res = self.client_for(self.evaluator).post(f'/api/v1/mrm/forms/{fid}/review/',
                                                   {'review_status': 'needs_revision', 'review_notes': 'Add a crew rest hazard'}, format='json')
        self.assertEqual(res.data['stage'], 'needs_revision')
        creator_view = self.client_for(self.creator).get(f'/api/v1/mrm/forms/{fid}/').data
        self.assertEqual(creator_view['can']['edit'], 'creator_revision')
        self.assertTrue(creator_view['can']['submit'])
        edit = self.client_for(self.creator).patch(f'/api/v1/mrm/forms/{fid}/', {
            'hazards': [{'hazard': str(self.h_low.id)}, {'hazard': str(self.h_mid.id)}]}, format='json')
        self.assertEqual(edit.status_code, 200, edit.data)
        self.assertFalse(edit.data['creator_signed'])   # signature cleared because content changed
        again = self.client_for(self.creator).post(f'/api/v1/mrm/forms/{fid}/submit/')
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.data['stage'], 'awaiting_review')
        kinds = [e['kind'] for e in again.data['events']]
        self.assertEqual(kinds.count('SUBMITTED'), 2)

    def test_edit_permissions(self):
        form = self.create_form()
        fid = form['id']
        self.assertEqual(self.client_for(self.creator2).patch(f'/api/v1/mrm/forms/{fid}/', {'activity_mission': 'x'}, format='json').status_code, 404)
        self.assertEqual(self.client_for(self.creator).patch(f'/api/v1/mrm/forms/{fid}/', {'activity_mission': 'Better name'}, format='json').status_code, 200)
        self.client_for(self.creator).post(f'/api/v1/mrm/forms/{fid}/submit/')
        # creator may still edit while the review is pending, but may no longer change the reviewer
        res = self.client_for(self.creator).patch(f'/api/v1/mrm/forms/{fid}/', {'reviewer': str(self.evaluator.id)}, format='json')
        self.assertEqual(res.status_code, 403)
        # the assigned evaluator may edit content
        res = self.client_for(self.evaluator).patch(f'/api/v1/mrm/forms/{fid}/', {'safety_objectives': 'Refined'}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertFalse(res.data['creator_signed'])

    def test_delete_rules(self):
        form = self.create_form()
        self.assertEqual(self.client_for(self.creator2).delete(f"/api/v1/mrm/forms/{form['id']}/").status_code, 404)
        self.assertEqual(self.client_for(self.creator).delete(f"/api/v1/mrm/forms/{form['id']}/").status_code, 204)
        self.assertEqual(self.client_for(self.creator).get(f"/api/v1/mrm/forms/{form['id']}/").status_code, 404)
        self.assertTrue(MRMForm.objects.filter(pk=form['id'], is_active=False).exists())   # archived, not erased
        sub = self.create_form()
        self.client_for(self.creator).post(f"/api/v1/mrm/forms/{sub['id']}/submit/")
        self.assertEqual(self.client_for(self.creator).delete(f"/api/v1/mrm/forms/{sub['id']}/").status_code, 403)
        self.assertEqual(self.client_for(self.admin).delete(f"/api/v1/mrm/forms/{sub['id']}/").status_code, 204)

    def test_late_signing(self):
        self.creator.signature.delete(save=True)
        form = self.create_form()
        res = self.client_for(self.creator).post(f"/api/v1/mrm/forms/{form['id']}/submit/")
        self.assertFalse(res.data['creator_signed'])
        self.assertTrue(res.data['warnings'])
        self.creator.signature.save('s.png', png_signature(), save=True)
        signed = self.client_for(self.creator).post(f"/api/v1/mrm/forms/{form['id']}/sign/")
        self.assertEqual(signed.status_code, 200, signed.data)
        self.assertTrue(signed.data['creator_signed'])


class VisibilityTests(MRMTestCase):
    def test_creator_sees_only_own_forms(self):
        mine = self.create_form()
        theirs = self.create_form(self.creator2)
        ids = {f['id'] for f in self.client_for(self.creator).get('/api/v1/mrm/forms/').data['results']}
        self.assertEqual(ids, {mine['id']})
        self.assertEqual(self.client_for(self.creator).get(f"/api/v1/mrm/forms/{theirs['id']}/").status_code, 404)

    def test_assigned_authority_with_creator_authority_can_open_the_form(self):
        """Legacy bug: designees whose authority was 'Creator' were blocked from the very form they had to approve."""
        form = self.create_form(hazards=[{'hazard': str(self.h_mid.id)}])
        self.advance_to_authority(form['id'])
        self.assertEqual(self.client_for(self.wing_cdr).get(f"/api/v1/mrm/forms/{form['id']}/").status_code, 200)
        self.assertIn('authority', self.client_for(self.wing_cdr).get(f"/api/v1/mrm/forms/{form['id']}/").data['my_roles'])

    def test_safety_officer_scope(self):
        form = self.create_form()
        self.assertEqual(self.client_for(self.uso).get(f"/api/v1/mrm/forms/{form['id']}/").status_code, 200)
        self.assertEqual(self.client_for(self.outsider_uso).get(f"/api/v1/mrm/forms/{form['id']}/").status_code, 404)
        # assignments widen a USO's scope
        from apps.mrm.models import SafetyOfficerAssignment
        SafetyOfficerAssignment.objects.create(user=self.outsider_uso, unit=self.sqn)
        self.assertEqual(self.client_for(self.outsider_uso).get(f"/api/v1/mrm/forms/{form['id']}/").status_code, 200)

    def test_admin_and_uoms_commander_see_everything(self):
        form = self.create_form()
        commander = make_user('cmdr', self.wing, role=User.Role.COMMANDER)
        for user in (self.admin, commander):
            self.assertEqual(self.client_for(user).get(f"/api/v1/mrm/forms/{form['id']}/").status_code, 200)

    def test_user_without_mrm_authority_sees_nothing_until_tagged_on_an_approved_form(self):
        form = self.create_form(tagged_personnel=[{'user': str(self.no_authority.id), 'role': 'Crew Member'}])
        c = self.client_for(self.no_authority)
        self.assertEqual(c.get('/api/v1/mrm/forms/').data['results'], [])
        self.advance_to_authority(form['id'])
        self.assertEqual(c.get('/api/v1/mrm/forms/').data['results'], [])   # not yet approved
        self.client_for(self.creator).post(f"/api/v1/mrm/forms/{form['id']}/approve/")
        self.assertEqual(len(c.get('/api/v1/mrm/forms/').data['results']), 1)

    def test_uoms_module_gate_applies(self):
        RolePermission.objects.filter(role='VIEWER', module=Module.MISSIONS).update(is_granted=False)
        blocked = make_user('viewer', self.sqn, role=User.Role.VIEWER, authority=A.CREATOR)
        self.assertEqual(self.client_for(blocked).get('/api/v1/mrm/forms/').status_code, 403)

    def test_unauthenticated(self):
        self.assertEqual(APIClient().get('/api/v1/mrm/forms/').status_code, 401)


class MissionIntegrationTests(MRMTestCase):
    def setUp(self):
        self.mission = Mission.objects.create(name='Operation Resupply', unit=self.sqn)

    def test_mrm_links_to_mission_and_drives_its_status(self):
        form = self.create_form(mission=str(self.mission.id), activity_mission='')
        self.assertEqual(form['activity_mission'], 'Operation Resupply')
        self.advance_to_authority(form['id'])
        self.mission.refresh_from_db()
        self.assertEqual(self.mission.risk_review_status, Mission.RiskReviewStatus.SUBMITTED)

        self.client_for(self.creator).post(f"/api/v1/mrm/forms/{form['id']}/approve/")
        self.mission.refresh_from_db()
        self.assertEqual(self.mission.risk_review_status, Mission.RiskReviewStatus.APPROVED)
        # MRM approval is a risk decision only — the mission's own approval is a separate workflow (apps.missions.ground)
        self.assertEqual(self.mission.status, Mission.Status.PLANNED)
        self.assertEqual(self.mission.approval_status, Mission.ApprovalStatus.DRAFT)
        self.assertGreaterEqual(self.mission.approval_logs.count(), 2)

        detail = self.client_for(self.admin).get(f'/api/v1/missions/profiles/{self.mission.id}/').data
        self.assertEqual(detail['mrm']['mrm_number'], form['mrm_number'])
        self.assertEqual(detail['mrm']['stage'], 'approved')
        self.assertEqual(detail['overall_risk_level'], 'MEDIUM')      # 3C before-rating
        self.assertEqual(detail['overall_residual_risk_level'], 'LOW')  # 1E residual -> Operator tier

    def test_rejection_reopens_mission_review(self):
        form = self.create_form(mission=str(self.mission.id))
        self.client_for(self.creator).post(f"/api/v1/mrm/forms/{form['id']}/submit/")
        self.client_for(self.evaluator).post(f"/api/v1/mrm/forms/{form['id']}/review/",
                                             {'review_status': 'rejected', 'review_notes': 'Unsafe plan'}, format='json')
        self.mission.refresh_from_db()
        self.assertEqual(self.mission.risk_review_status, Mission.RiskReviewStatus.REJECTED)
        self.assertEqual(self.mission.review_comments, 'Unsafe plan')

    def test_old_mission_approval_endpoints_defer_to_the_mrm(self):
        self.create_form(mission=str(self.mission.id))
        c = self.client_for(self.admin)
        for action in ('submit-for-approval', 'approve', 'reject'):
            res = c.post(f'/api/v1/missions/profiles/{self.mission.id}/{action}/', {'comments': 'x'}, format='json')
            self.assertEqual(res.status_code, 400, action)
            self.assertIn('MRM', str(res.data))

    def test_enforcement_flag_blocks_quick_approval_for_missions_without_an_mrm(self):
        c = self.client_for(self.admin)
        default = c.post(f'/api/v1/missions/profiles/{self.mission.id}/submit-for-approval/', {}, format='json')
        self.assertNotIn('MRM', str(default.data))   # default: the legacy rule (needs a hazard assessment) applies, not the MRM gate
        other = Mission.objects.create(name='Other op', unit=self.sqn)
        with override_settings(MRM_REQUIRE_FOR_MISSION_APPROVAL=True):
            res = c.post(f'/api/v1/missions/profiles/{other.id}/submit-for-approval/', {}, format='json')
            self.assertEqual(res.status_code, 400)
            self.assertIn('require an MRM', str(res.data))

    def test_one_active_mrm_per_mission(self):
        self.create_form(mission=str(self.mission.id))
        res = self.client_for(self.creator).post('/api/v1/mrm/forms/', self.payload(mission=str(self.mission.id)), format='json')
        self.assertEqual(res.status_code, 400)

    def test_archiving_the_mrm_returns_mission_to_draft(self):
        form = self.create_form(mission=str(self.mission.id))
        self.client_for(self.creator).post(f"/api/v1/mrm/forms/{form['id']}/submit/")
        self.client_for(self.admin).delete(f"/api/v1/mrm/forms/{form['id']}/")
        self.mission.refresh_from_db()
        self.assertEqual(self.mission.risk_review_status, Mission.RiskReviewStatus.DRAFT)

    def test_elevated_risk_raises_and_clears_a_dashboard_alert(self):
        from apps.risk.models import RiskAlert
        form = self.create_form(mission=str(self.mission.id), hazards=[{'hazard': str(self.h_high.id)}])   # 100% -> Commander
        self.client_for(self.creator).post(f"/api/v1/mrm/forms/{form['id']}/submit/")
        alert = RiskAlert.objects.get(title__startswith=f"[MRM {form['mrm_number']}]")
        self.assertEqual(alert.severity, 'CRITICAL')
        self.assertFalse(alert.is_resolved)
        self.client_for(self.evaluator).post(f"/api/v1/mrm/forms/{form['id']}/review/",
                                             {'review_status': 'rejected', 'review_notes': 'No'}, format='json')
        alert.refresh_from_db()
        self.assertTrue(alert.is_resolved)


class FeedbackTests(MRMTestCase):
    def approved_form(self):
        form = self.create_form(tagged_personnel=[{'user': str(self.creator2.id), 'role': 'Crew Member'}])
        self.advance_to_authority(form['id'])
        self.client_for(self.creator).post(f"/api/v1/mrm/forms/{form['id']}/approve/")
        return form

    def test_only_tagged_users_on_approved_forms_can_give_feedback_once(self):
        form = self.create_form(tagged_personnel=[{'user': str(self.creator2.id), 'role': 'Crew Member'}])
        url = f"/api/v1/mrm/forms/{form['id']}/feedback/"
        body = {'risk_assessment_accuracy': 4, 'hazard_identification_rating': 5, 'mitigation_effectiveness': 3,
                'what_went_well': 'All good', 'new_hazards_identified': 'Bird strike risk', 'recommend_add_to_hazard_registry': True,
                'recommended_hazard_description': 'Bird strike on approach', 'recommended_mitigations': 'Bird patrol'}
        self.assertEqual(self.client_for(self.creator2).post(url, body, format='json').status_code, 404)  # not visible yet
        self.advance_to_authority(form['id'])
        self.client_for(self.creator).post(f"/api/v1/mrm/forms/{form['id']}/approve/")
        self.assertEqual(self.client_for(self.other_creator).post(url, body, format='json').status_code, 404)
        self.assertEqual(self.client_for(self.creator2).post(url, {**body, 'risk_assessment_accuracy': 9}, format='json').status_code, 400)
        ok = self.client_for(self.creator2).post(url, body, format='json')
        self.assertEqual(ok.status_code, 201, ok.data)
        self.assertEqual(self.client_for(self.creator2).post(url, body, format='json').status_code, 400)  # only once

    def test_uso_review_and_hazard_creation_requires_explicit_ratings(self):
        form = self.approved_form()
        fb = self.client_for(self.creator2).post(f"/api/v1/mrm/forms/{form['id']}/feedback/", {
            'new_hazards_identified': 'Bird strike', 'recommend_add_to_hazard_registry': True,
            'recommended_hazard_description': 'Bird strike on approach', 'recommended_mitigations': 'Bird patrol'}, format='json').data
        c = self.client_for(self.uso)
        self.assertEqual(c.get('/api/v1/mrm/feedback/pending-count/').data['count'], 1)
        self.assertEqual(self.client_for(self.outsider_uso).get(f"/api/v1/mrm/feedback/{fb['id']}/").status_code, 404)

        no_ratings = c.post(f"/api/v1/mrm/feedback/{fb['id']}/review/", {
            'action': 'take_action', 'action_taken': 'Added to registry', 'new_hazard': {'hazard_description': 'Bird strike'}}, format='json')
        self.assertEqual(no_ratings.status_code, 400)
        res = c.post(f"/api/v1/mrm/feedback/{fb['id']}/review/", {
            'action': 'take_action', 'action_taken': 'Added to registry',
            'new_hazard': {'before_likelihood': 3, 'before_severity': 'B', 'after_likelihood': 2, 'after_severity': 'C'}}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['status'], 'action_taken')
        created = Hazard.objects.get(pk=res.data['created_hazard'])
        self.assertEqual((created.before_risk_rating, created.after_risk_rating, created.unit_id), ('3B', '2C', self.sqn.id))
        self.assertEqual(c.get('/api/v1/mrm/feedback/pending-count/').data['count'], 0)

    def test_anonymous_feedback_hides_the_author_from_reviewers(self):
        form = self.approved_form()
        self.client_for(self.creator2).post(f"/api/v1/mrm/forms/{form['id']}/feedback/", {'is_anonymous': True, 'what_went_well': 'x'}, format='json')
        item = self.client_for(self.uso).get('/api/v1/mrm/feedback/').data['results'][0]
        self.assertIsNone(item['submitted_by'])

    def test_close_feedback(self):
        form = self.approved_form()
        self.assertEqual(self.client_for(self.creator2).post(f"/api/v1/mrm/forms/{form['id']}/close-feedback/").status_code, 403)
        self.assertEqual(self.client_for(self.creator).post(f"/api/v1/mrm/forms/{form['id']}/close-feedback/").status_code, 200)
        res = self.client_for(self.creator2).post(f"/api/v1/mrm/forms/{form['id']}/feedback/", {'what_went_well': 'x'}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_my_feedback_dashboard(self):
        self.approved_form()
        data = self.client_for(self.creator2).get('/api/v1/mrm/feedback/mine/').data
        self.assertEqual(data['stats']['pending_feedback'], 1)


class SafetyOfficerAndAdminTests(MRMTestCase):
    def test_uso_manages_users_only_in_scope_and_never_admins(self):
        c = self.client_for(self.uso)
        usernames = {u['username'] for u in c.get('/api/v1/mrm/safety/users/').data['results']}
        self.assertIn('creator', usernames)
        self.assertNotIn('other', usernames)
        toggle = c.post(f'/api/v1/mrm/safety/users/{self.creator2.id}/toggle-active/')
        self.assertFalse(toggle.data['is_active'])
        self.assertEqual(c.post(f'/api/v1/mrm/safety/users/{self.uso.id}/toggle-active/').status_code, 400)  # not yourself
        self.assertEqual(c.post(f'/api/v1/mrm/safety/users/{self.other_creator.id}/toggle-active/').status_code, 404)
        admin_in_unit = make_user('unitadmin', self.sqn, authority=A.ADMINISTRATOR)
        self.assertEqual(c.post(f'/api/v1/mrm/safety/users/{admin_in_unit.id}/reset-password/',
                                {'new_password': 'Another-Str0ng-pass', 'confirm_password': 'Another-Str0ng-pass'}, format='json').status_code, 403)
        ok = c.post(f'/api/v1/mrm/safety/users/{self.creator.id}/reset-password/',
                    {'new_password': 'Another-Str0ng-pass', 'confirm_password': 'Another-Str0ng-pass'}, format='json')
        self.assertEqual(ok.status_code, 200, ok.data)
        self.creator.refresh_from_db()
        self.assertTrue(self.creator.must_change_password)

    def test_regular_users_cannot_use_safety_tools(self):
        self.assertEqual(self.client_for(self.creator).get('/api/v1/mrm/safety/users/').status_code, 403)
        self.assertEqual(self.client_for(self.creator).get('/api/v1/mrm/analytics/').status_code, 403)

    def test_assignments_are_admin_only_and_uso_only(self):
        body = {'user': str(self.outsider_uso.id), 'unit': str(self.sqn.id)}
        self.assertEqual(self.client_for(self.uso).post('/api/v1/mrm/safety/assignments/', body, format='json').status_code, 403)
        self.assertEqual(self.client_for(self.admin).post('/api/v1/mrm/safety/assignments/',
                         {'user': str(self.creator.id), 'unit': str(self.sqn.id)}, format='json').status_code, 400)
        self.assertEqual(self.client_for(self.admin).post('/api/v1/mrm/safety/assignments/', body, format='json').status_code, 201)

    def test_analytics(self):
        form = self.create_form(tagged_personnel=[{'user': str(self.creator2.id), 'role': 'Crew Member'}])
        self.advance_to_authority(form['id'])
        self.client_for(self.creator).post(f"/api/v1/mrm/forms/{form['id']}/approve/")
        data = self.client_for(self.uso).get('/api/v1/mrm/analytics/').data
        self.assertEqual(data['totals']['forms'], 1)
        self.assertEqual(data['totals']['approved'], 1)
        self.assertEqual(self.client_for(self.outsider_uso).get('/api/v1/mrm/analytics/').data['totals']['forms'], 0)

    def test_work_queue(self):
        form = self.create_form()
        self.client_for(self.creator).post(f"/api/v1/mrm/forms/{form['id']}/submit/")
        self.assertEqual(self.client_for(self.evaluator).get('/api/v1/mrm/work-queue/').data['awaiting_my_review'], 1)

    def test_signature_upload_validation(self):
        c = self.client_for(self.creator2)
        bad = c.post('/api/v1/mrm/signature/', {'signature': SimpleUploadedFile('x.png', b'not an image', content_type='image/png')}, format='multipart')
        self.assertEqual(bad.status_code, 400)
        ok = c.post('/api/v1/mrm/signature/', {'signature': png_signature()}, format='multipart')
        self.assertEqual(ok.status_code, 200)
        self.creator2.refresh_from_db()
        self.assertTrue(self.creator2.signature)
        self.assertTrue(c.get('/api/v1/mrm/me/').data['has_signature'])

    def test_unit_logo_permissions(self):
        self.assertEqual(self.client_for(self.creator).post('/api/v1/mrm/unit-logos/', {'unit': str(self.sqn.id), 'image': png_signature()}, format='multipart').status_code, 403)
        self.assertEqual(self.client_for(self.outsider_uso).post('/api/v1/mrm/unit-logos/', {'unit': str(self.sqn.id), 'image': png_signature()}, format='multipart').status_code, 403)
        ok = self.client_for(self.uso).post('/api/v1/mrm/unit-logos/', {'unit': str(self.sqn.id), 'image': png_signature()}, format='multipart')
        self.assertEqual(ok.status_code, 201, ok.data)


class AccountSecurityTests(MRMTestCase):
    def test_me_endpoint_cannot_escalate_privileges(self):
        """Regression: PATCH /auth/me/ used the full UserSerializer, so anyone could make themselves ADMIN."""
        c = self.client_for(self.creator)
        res = c.patch('/api/v1/auth/me/', {'role': 'ADMIN', 'mrm_authority': 'ADMINISTRATOR', 'is_active': True,
                                           'phone_number': '0917', 'unit': str(self.other_sqn.id)}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.creator.refresh_from_db()
        self.assertEqual(self.creator.role, User.Role.VIEWER)
        self.assertEqual(self.creator.mrm_authority, A.CREATOR)
        self.assertEqual(self.creator.unit_id, self.sqn.id)
        self.assertEqual(self.creator.phone_number, '0917')   # allowed field did change
        self.assertEqual(res.data['effective_mrm_authority'], A.CREATOR)

    def test_pdf_renders_with_hazards_logo_and_signatures(self):
        from apps.mrm.models import UnitLogo
        from apps.mrm.pdf import generate_pdf
        UnitLogo.objects.create(unit=self.sqn, image=png_signature('logo.png'))
        form = self.create_form(hazards=[{'hazard': str(h.id)} for h in (self.h_low, self.h_mid, self.h_high)],
                                tagged_personnel=[{'user': str(self.creator2.id), 'role': 'Crew Member'}])
        pdf = generate_pdf(MRMForm.objects.get(pk=form['id']))
        self.assertEqual(pdf[:4], b'%PDF')
        self.assertGreater(len(pdf), 5000)
