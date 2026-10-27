"""Category-driven mission planning: Ground Operations form, personnel, vehicles/itineraries/POV, authority approval, MRM hand-off."""
from unittest import mock

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import AuditLog, Notification
from apps.missions.models import Mission, MissionApprovalLog, MissionItinerary, MissionPersonnel, MissionVehicle
from apps.mrm.tests.test_mrm import A, D, MRMTestCase, make_user
from apps.personnel.models import Personnel, Rank, Section
from apps.vehicles.models import Trip, Vehicle

BASE = '/api/v1/missions/profiles'
START = '2026-11-01T06:00:00Z'
END = '2026-11-01T18:00:00Z'


class PlanningCase(MRMTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        call_command('seed_permissions', stdout=open('/dev/null', 'w'))      # the real default RBAC matrix
        rank = Rank.objects.create(name='Sergeant', abbreviation='SGT', order=10)

        def person(n, account=None, unit=None):
            return Personnel.objects.create(
                service_number=f'SN-{n}', first_name=f'First{n}', last_name=f'Last{n}', rank=rank,
                unit=unit or cls.sqn, linked_account=account)

        # the mission planner: STAFF role may create/edit missions
        cls.planner = make_user('planner', cls.sqn, role=User.Role.STAFF, authority=A.CREATOR, signed=True)
        # approving authority: a COMMANDER-role user in the parent Wing (holds MISSIONS:APPROVE)
        cls.cdr = make_user('cdr', cls.wing, role=User.Role.COMMANDER, designation=D.SQUADRON_COMMANDER)
        cls.cdr2 = make_user('cdr2', cls.sqn, role=User.Role.COMMANDER, designation=D.COMMANDER)
        # a designated commander whose role lacks the approve permission must not be offered
        cls.staff_cdr = make_user('staffcdr', cls.sqn, role=User.Role.STAFF, designation=D.SQUADRON_COMMANDER)

        cls.p_leader = person(1)
        cls.p_member = person(2)
        cls.p_driver = person(3)
        cls.p_mrm = person(4, account=cls.creator)            # creator has MRM Creator authority -> eligible MRM preparer
        cls.p_noacct = person(5)                              # no login account -> cannot prepare an MRM
        cls.p_other_unit = person(6, unit=cls.other_sqn)
        cls.p_crew_account = person(7, account=cls.creator2)

        cls.section = Section.objects.create(name='S3 Operations', code='S3', unit=cls.sqn)
        cls.foreign_section = Section.objects.create(name='S3 Ops (102)', code='S3B', unit=cls.other_sqn)

        cls.truck = Vehicle.objects.create(plate_number='SAA 111', vehicle_type='Truck', make='Isuzu', model='Elf', odometer_km=1000)
        cls.jeep = Vehicle.objects.create(plate_number='SBB 222', vehicle_type='Jeep', make='Toyota', model='Land Cruiser', odometer_km=5000)

    # --- payload helpers ------------------------------------------------------------------
    def crew(self, extra=()):
        rows = [
            {'personnel': str(self.p_leader.id), 'role': 'TEAM_LEADER'},
            {'personnel': str(self.p_member.id), 'role': 'TEAM_MEMBER'},
            {'personnel': str(self.p_driver.id), 'role': 'DRIVER'},
            {'personnel': str(self.p_mrm.id), 'role': 'ASSISTANT_TEAM_LEADER'},
        ]
        return rows + list(extra)

    def leg(self, **kw):
        leg = {
            'origin': {'name': 'Camp', 'lat': 8.4822, 'lng': 124.6472},
            'destination': {'name': 'Checkpoint 4', 'lat': 8.5100, 'lng': 124.7000},
            'stops': [{'name': 'Bridge', 'lat': 8.495, 'lng': 124.67}],
        }
        leg.update(kw)
        return leg

    def payload(self, **over):
        data = {
            'category': 'GROUND_OPERATIONS', 'name': 'Convoy to Checkpoint 4', 'description': 'Resupply',
            'start_date': START, 'end_date': END, 'unit': str(self.sqn.id), 'responsible_section': str(self.section.id),
            'personnel': self.crew(),
        }
        data.update(over)
        return data

    def create(self, user=None, expect=201, **over):
        res = self.client_for(user or self.planner).post(f'{BASE}/', self.payload(**over), format='json')
        self.assertEqual(res.status_code, expect, res.data)
        return res.data

    def ready_payload(self, **over):
        return self.payload(approval_authority=str(self.cdr.id), mrm_assignee=str(self.p_mrm.id), **over)

    def submit(self, mission_id, user=None):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client_for(user or self.planner).post(f'{BASE}/{mission_id}/submit-mission/')

    def submitted_mission(self, **over):
        data = self.create(**{'approval_authority': str(self.cdr.id), 'mrm_assignee': str(self.p_mrm.id), **over})
        res = self.submit(data['id'])
        self.assertEqual(res.status_code, 200, res.data)
        return res.data


class CategoryTests(PlanningCase):
    def test_categories_catalog_has_air_prepared_but_disabled(self):
        data = self.client_for(self.planner).get(f'{BASE}/categories/').data
        by_key = {c['key']: c for c in data['categories']}
        self.assertTrue(by_key['GROUND_OPERATIONS']['enabled'])
        self.assertFalse(by_key['AIR_OPERATIONS']['enabled'])
        self.assertEqual({r['value'] for r in data['roles']}, {'TEAM_LEADER', 'ASSISTANT_TEAM_LEADER', 'TEAM_MEMBER', 'DRIVER', 'OTHER'})

    def test_category_is_required_on_create(self):
        res = self.client_for(self.planner).post(f'{BASE}/', {'name': 'x'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('category', res.data)

    def test_air_operations_cannot_be_created_until_specified_but_does_not_break_ground(self):
        res = self.client_for(self.planner).post(f'{BASE}/', {'category': 'AIR_OPERATIONS', 'name': 'Sortie'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('category', res.data)
        self.assertEqual(self.create()['category'], 'GROUND_OPERATIONS')

    def test_unknown_category_rejected(self):
        self.assertEqual(self.client_for(self.planner).post(f'{BASE}/', {'category': 'SPACE_OPS'}, format='json').status_code, 400)

    def test_category_cannot_be_changed_later(self):
        m = self.create()
        res = self.client_for(self.planner).patch(f"{BASE}/{m['id']}/", {'category': 'AIR_OPERATIONS', 'name': 'z'}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_users_without_create_permission_cannot_create(self):
        res = self.client_for(self.no_authority).post(f'{BASE}/', self.payload(), format='json')
        self.assertEqual(res.status_code, 403)


class GroundFormValidationTests(PlanningCase):
    def errors(self, **over):
        res = self.client_for(self.planner).post(f'{BASE}/', self.payload(**over), format='json')
        self.assertEqual(res.status_code, 400, res.data)
        return res.data

    def test_happy_path_saves_and_returns_every_section(self):
        m = self.create()
        self.assertEqual(m['name'], 'Convoy to Checkpoint 4')
        self.assertEqual(m['category_label'], 'Ground Operations')
        self.assertEqual(m['responsible_section_name'], 'S3 Operations')
        self.assertEqual(m['approval']['status'], 'DRAFT')
        self.assertEqual({p['role'] for p in m['personnel']}, {'TEAM_LEADER', 'TEAM_MEMBER', 'DRIVER', 'ASSISTANT_TEAM_LEADER'})
        self.assertEqual(m['mrm_preparation']['status'], 'NOT_STARTED')
        self.assertEqual(Mission.objects.get(pk=m['id']).created_by_id, self.planner.id)

    def test_required_fields(self):
        data = self.errors(name='', start_date=None, end_date=None, unit=None, responsible_section=None, personnel=[])
        for key in ('name', 'start_date', 'end_date', 'unit', 'responsible_section', 'personnel'):
            self.assertIn(key, data)

    def test_end_must_not_precede_start(self):
        self.assertIn('end_date', self.errors(start_date=END, end_date=START))
        self.create(start_date=START, end_date=START)     # equal is fine

    def test_section_must_belong_to_the_selected_unit(self):
        data = self.errors(responsible_section=str(self.foreign_section.id))
        self.assertIn('does not belong to', str(data['responsible_section']))

    def test_unit_must_be_in_scope(self):
        self.assertIn('unit', self.errors(unit=str(self.other_sqn.id), responsible_section=str(self.foreign_section.id)))

    def test_personnel_rules(self):
        dup = self.errors(personnel=self.crew([{'personnel': str(self.p_member.id), 'role': 'DRIVER'}]))
        self.assertIn('already assigned', str(dup))
        none_leader = self.errors(personnel=[{'personnel': str(self.p_member.id), 'role': 'TEAM_MEMBER'}])
        self.assertIn('Team Leader', str(none_leader['personnel']))
        two = self.errors(personnel=self.crew([{'personnel': str(self.p_noacct.id), 'role': 'TEAM_LEADER'}]))
        self.assertIn('Only one', str(two['personnel']))
        other = self.errors(personnel=self.crew([{'personnel': str(self.p_noacct.id), 'role': 'OTHER'}]))
        self.assertIn('personnel[4].role_other', other)
        bad_role = self.errors(personnel=self.crew([{'personnel': str(self.p_noacct.id), 'role': 'WIZARD'}]))
        self.assertIn('personnel[4].role', bad_role)
        out_of_scope = self.errors(personnel=self.crew([{'personnel': str(self.p_other_unit.id), 'role': 'TEAM_MEMBER'}]))
        self.assertIn('outside your scope', str(out_of_scope))

    def test_other_role_with_description_is_saved(self):
        m = self.create(personnel=self.crew([{'personnel': str(self.p_noacct.id), 'role': 'OTHER', 'role_other': 'Medic'}]))
        labels = {p['person']['name']: p['role_label'] for p in m['personnel']}
        self.assertEqual(labels[self.p_noacct.full_name], 'Medic')

    def test_nothing_is_saved_when_any_part_is_invalid(self):
        before = (Mission.objects.count(), MissionPersonnel.objects.count())
        self.errors(vehicles=[{'is_pov': False, 'vehicle': None}])
        self.assertEqual(before, (Mission.objects.count(), MissionPersonnel.objects.count()))

    def test_errors_are_keyed_by_field_path_so_the_ui_can_show_them_beside_the_field(self):
        data = self.errors(vehicles=[{'is_pov': True, 'pov': {}, 'itinerary': [
            {'origin': {'name': 'A', 'mgrs': 'nonsense'}, 'destination': {'name': '', 'lat': 99, 'lng': 0}}]}])
        self.assertIn('vehicles[0].pov.plate_number', data)
        self.assertIn('vehicles[0].pov.vehicle_type', data)
        self.assertIn('vehicles[0].itinerary[0].origin.mgrs', data)
        self.assertIn('vehicles[0].itinerary[0].destination.name', data)
        self.assertIn('vehicles[0].itinerary[0].destination.location', data)


class VehicleItineraryTests(PlanningCase):
    def fleet(self, vehicle, **kw):
        return {'is_pov': False, 'vehicle': str(vehicle.id), 'itinerary': [self.leg()], **kw}

    def test_a_mission_may_have_no_vehicle(self):
        self.assertEqual(self.create()['vehicles'], [])

    def test_several_vehicles_each_with_several_legs_and_stops(self):
        m = self.create(vehicles=[
            {**self.fleet(self.truck), 'driver': str(self.p_driver.id), 'itinerary': [
                self.leg(), self.leg(origin={'name': 'Checkpoint 4', 'lat': 8.51, 'lng': 124.70}, destination={'name': 'Camp', 'lat': 8.4822, 'lng': 124.6472}, stops=[])]},
            self.fleet(self.jeep),
        ])
        self.assertEqual(len(m['vehicles']), 2)
        truck = m['vehicles'][0]
        self.assertEqual(truck['fleet']['plate_number'], 'SAA 111')
        self.assertEqual(truck['driver_name'], self.p_driver.full_name)
        self.assertEqual([leg['sequence'] for leg in truck['itinerary']], [1, 2])
        self.assertEqual(truck['itinerary'][0]['stops'][0]['name'], 'Bridge')
        self.assertTrue(truck['itinerary'][0]['origin']['mgrs'])           # MGRS derived and stored
        self.assertEqual(round(truck['itinerary'][0]['destination']['lat'], 4), 8.51)
        self.assertEqual(m['vehicles'][1]['fleet']['plate_number'], 'SBB 222')

    def test_data_persists_across_a_fresh_fetch(self):
        m = self.create(vehicles=[self.fleet(self.truck)])
        fetched = self.client_for(self.planner).get(f"{BASE}/{m['id']}/").data
        self.assertEqual(fetched['vehicles'][0]['itinerary'][0]['destination']['name'], 'Checkpoint 4')
        self.assertEqual(fetched['personnel'], m['personnel'])

    def test_mgrs_only_entry_is_accepted_and_converted(self):
        from apps.gis.utils import latlon_to_mgrs
        mgrs = latlon_to_mgrs(8.4822, 124.6472)
        m = self.create(vehicles=[{'is_pov': False, 'vehicle': str(self.truck.id), 'itinerary': [self.leg(origin={'name': 'Camp', 'mgrs': mgrs})]}])
        origin = m['vehicles'][0]['itinerary'][0]['origin']
        self.assertAlmostEqual(origin['lat'], 8.4822, places=3)
        self.assertAlmostEqual(origin['lng'], 124.6472, places=3)

    def test_invalid_mgrs_gives_a_readable_message(self):
        res = self.client_for(self.planner).post(f'{BASE}/', self.payload(vehicles=[
            {'is_pov': False, 'vehicle': str(self.truck.id), 'itinerary': [self.leg(origin={'name': 'x', 'mgrs': '51N ZZ 123'})]}]), format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('not a valid MGRS', str(res.data['vehicles[0].itinerary[0].origin.mgrs']))

    def test_map_position_and_mgrs_must_agree(self):
        from apps.gis.utils import latlon_to_mgrs
        far = latlon_to_mgrs(9.5, 125.5)
        res = self.client_for(self.planner).post(f'{BASE}/', self.payload(vehicles=[
            {'is_pov': False, 'vehicle': str(self.truck.id), 'itinerary': [self.leg(origin={'name': 'x', 'lat': 8.48, 'lng': 124.64, 'mgrs': far})]}]), format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('apart', str(res.data))

    def test_pov_needs_no_odometer_and_never_touches_the_fleet(self):
        odometers = dict(Vehicle.objects.values_list('plate_number', 'odometer_km'))
        trips = Trip.objects.count()
        m = self.create(vehicles=[{'is_pov': True, 'pov': {'plate_number': 'pov 999', 'vehicle_type': 'Sedan', 'make': 'Honda', 'model': 'Civic',
                                                           'owner_name': 'S. Reyes'}, 'itinerary': [self.leg()]}])
        pov = m['vehicles'][0]
        self.assertTrue(pov['is_pov'])
        self.assertIsNone(pov['vehicle'])
        self.assertIsNone(pov['fleet'])
        self.assertEqual(pov['pov']['plate_number'], 'POV 999')                # normalised
        self.assertEqual(dict(Vehicle.objects.values_list('plate_number', 'odometer_km')), odometers)
        self.assertEqual(Trip.objects.count(), trips)
        self.assertEqual(Vehicle.objects.count(), 2)                           # no fleet record was created for the POV
        self.assertFalse(any('odometer' in f.name for f in MissionVehicle._meta.get_fields()))

    def test_a_fleet_plate_cannot_be_entered_as_a_pov(self):
        res = self.client_for(self.planner).post(f'{BASE}/', self.payload(vehicles=[
            {'is_pov': True, 'pov': {'plate_number': 'saa 111', 'vehicle_type': 'Truck'}}]), format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('official fleet vehicle', str(res.data))

    def test_duplicate_vehicles_and_povs_rejected(self):
        res = self.client_for(self.planner).post(f'{BASE}/', self.payload(vehicles=[self.fleet(self.truck), self.fleet(self.truck)]), format='json')
        self.assertIn('already on this mission', str(res.data))
        pov = {'is_pov': True, 'pov': {'plate_number': 'P1', 'vehicle_type': 'Car'}}
        res = self.client_for(self.planner).post(f'{BASE}/', self.payload(vehicles=[pov, pov]), format='json')
        self.assertIn('already on this mission', str(res.data))

    def test_driver_must_be_on_the_crew(self):
        res = self.client_for(self.planner).post(f'{BASE}/', self.payload(vehicles=[{**self.fleet(self.truck), 'driver': str(self.p_noacct.id)}]), format='json')
        self.assertIn('vehicles[0].driver', res.data)

    def test_arrival_before_departure_rejected(self):
        res = self.client_for(self.planner).post(f'{BASE}/', self.payload(vehicles=[{**self.fleet(self.truck), 'itinerary': [
            self.leg(planned_departure=END, planned_arrival=START)]}]), format='json')
        self.assertIn('vehicles[0].itinerary[0].planned_arrival', res.data)

    def test_editing_replaces_vehicles_without_duplicates(self):
        m = self.create(vehicles=[self.fleet(self.truck)])
        for _ in range(3):
            res = self.client_for(self.planner).patch(f"{BASE}/{m['id']}/", {'vehicles': [self.fleet(self.truck), self.fleet(self.jeep)]}, format='json')
            self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(MissionVehicle.objects.filter(mission_id=m['id']).count(), 2)
        self.assertEqual(MissionItinerary.objects.filter(vehicle_assignment__mission_id=m['id']).count(), 2)
        res = self.client_for(self.planner).patch(f"{BASE}/{m['id']}/", {'vehicles': []}, format='json')
        self.assertEqual(res.data['vehicles'], [])

    def test_partial_update_keeps_everything_not_mentioned(self):
        m = self.create(vehicles=[self.fleet(self.truck)])
        res = self.client_for(self.planner).patch(f"{BASE}/{m['id']}/", {'name': 'Renamed'}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['name'], 'Renamed')
        self.assertEqual(len(res.data['personnel']), 4)
        self.assertEqual(len(res.data['vehicles']), 1)
        self.assertEqual(res.data['vehicles'][0]['itinerary'][0]['stops'][0]['name'], 'Bridge')


class IdempotencyTests(PlanningCase):
    def test_repeating_a_create_with_the_same_token_never_makes_a_second_mission(self):
        token = '3f2b1c3e-8c1a-4a6e-9f7e-1b2c3d4e5f60'
        first = self.client_for(self.planner).post(f'{BASE}/', self.payload(client_request_id=token), format='json')
        again = self.client_for(self.planner).post(f'{BASE}/', self.payload(client_request_id=token), format='json')
        self.assertEqual((first.status_code, again.status_code), (201, 200))
        self.assertEqual(first.data['id'], again.data['id'])
        self.assertEqual(Mission.objects.filter(client_request_id=token).count(), 1)
        self.assertEqual(MissionPersonnel.objects.filter(mission_id=first.data['id']).count(), 4)

    def test_another_users_token_is_refused_even_for_admins(self):
        token = '9a2b1c3e-8c1a-4a6e-9f7e-1b2c3d4e5f61'
        self.client_for(self.planner).post(f'{BASE}/', self.payload(client_request_id=token), format='json')
        other = make_user('other_staff', self.sqn, role=User.Role.STAFF, authority=A.CREATOR)
        self.assertEqual(self.client_for(other).post(f'{BASE}/', self.payload(client_request_id=token), format='json').status_code, 403)
        self.assertEqual(self.client_for(self.admin).post(f'{BASE}/', self.payload(client_request_id=token), format='json').status_code, 403)

    def test_malformed_token_is_a_400(self):
        self.assertEqual(self.client_for(self.planner).post(f'{BASE}/', self.payload(client_request_id='not-a-uuid'), format='json').status_code, 400)


class AuthorityAndSubmissionTests(PlanningCase):
    def test_authority_candidates_use_the_hierarchy_and_the_approve_permission(self):
        res = self.client_for(self.planner).get(f'{BASE}/authorities/?unit={self.sqn.id}')
        names = [a['name'] for a in res.data]
        self.assertEqual(res.status_code, 200)
        self.assertIn(self.cdr.display_name_with_rank, names)        # parent-unit commander
        self.assertIn(self.cdr2.display_name_with_rank, names)       # same-unit commander
        self.assertNotIn(self.staff_cdr.display_name_with_rank, names)   # designated, but no MISSIONS:APPROVE
        self.assertNotIn(self.planner.display_name_with_rank, names)
        self.assertEqual(res.data[0]['name'], self.cdr2.display_name_with_rank)   # nearest unit first
        self.assertEqual(self.client_for(self.planner).get(f'{BASE}/authorities/').status_code, 400)
        self.assertEqual(self.client_for(self.planner).get(f'{BASE}/authorities/?unit={self.other_sqn.id}').status_code, 403)

    def test_an_ineligible_authority_cannot_be_selected(self):
        res = self.client_for(self.planner).post(f'{BASE}/', self.payload(approval_authority=str(self.staff_cdr.id)), format='json')
        self.assertIn('approval_authority', res.data)
        res = self.client_for(self.planner).post(f'{BASE}/', self.payload(approval_authority=str(self.planner.id)), format='json')
        self.assertIn('approval_authority', res.data)

    def test_mrm_assignee_must_be_crew_and_eligible(self):
        outside = self.client_for(self.planner).post(f'{BASE}/', self.payload(mrm_assignee=str(self.p_crew_account.id)), format='json')
        self.assertIn('assigned to this mission', str(outside.data['mrm_assignee']))
        no_account = self.client_for(self.planner).post(
            f'{BASE}/', self.payload(personnel=self.crew([{'personnel': str(self.p_noacct.id), 'role': 'TEAM_MEMBER'}]), mrm_assignee=str(self.p_noacct.id)), format='json')
        self.assertIn('cannot prepare MRM', str(no_account.data['mrm_assignee']))

    def test_submit_requires_an_authority_and_an_mrm_assignee(self):
        m = self.create()
        res = self.submit(m['id'])
        self.assertEqual(res.status_code, 400)
        self.assertIn('approval_authority', res.data)
        self.assertIn('mrm_assignee', res.data)
        self.assertEqual(Mission.objects.get(pk=m['id']).approval_status, 'DRAFT')
        self.assertEqual(Notification.objects.count(), 0)

    def test_submit_sets_pending_and_notifies_the_authority_and_the_mrm_assignee(self):
        m = self.submitted_mission()
        self.assertEqual(m['approval']['status'], 'PENDING')
        self.assertTrue(m['newly_submitted'])
        auth = Notification.objects.get(user=self.cdr)
        self.assertEqual(auth.kind, 'MISSION_APPROVAL_REQUEST')
        self.assertEqual(auth.link, f"/missions/{m['id']}")
        mrm = Notification.objects.get(user=self.creator)           # creator account is the linked MRM assignee
        self.assertEqual(mrm.kind, 'MRM_PREPARATION_REQUEST')
        self.assertEqual(mrm.link, f"/mrm/new?mission={m['id']}")
        self.assertEqual(Notification.objects.count(), 2)

    def test_resubmitting_a_pending_mission_is_idempotent(self):
        m = self.submitted_mission()
        again = self.submit(m['id'])
        self.assertEqual(again.status_code, 200)
        self.assertFalse(again.data['newly_submitted'])
        self.assertEqual(Notification.objects.count(), 2)
        self.assertEqual(MissionApprovalLog.objects.filter(mission_id=m['id'], workflow='MISSION_APPROVAL', action='SUBMITTED').count(), 1)

    def test_no_notification_when_the_transaction_rolls_back(self):
        m = self.create(approval_authority=str(self.cdr.id), mrm_assignee=str(self.p_mrm.id))
        with mock.patch('apps.missions.ground.log_action', side_effect=RuntimeError('db blew up')):
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertRaises(RuntimeError):
                    self.client_for(self.planner).post(f"{BASE}/{m['id']}/submit-mission/")
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(Mission.objects.get(pk=m['id']).approval_status, 'DRAFT')

    def test_only_the_creator_may_submit(self):
        m = self.create(approval_authority=str(self.cdr.id), mrm_assignee=str(self.p_mrm.id))
        other = make_user('other_staff', self.sqn, role=User.Role.STAFF, authority=A.CREATOR)
        self.assertEqual(self.submit(m['id'], other).status_code, 403)    # a same-unit colleague can see it but not submit it
        self.assertEqual(self.submit(m['id'], self.cdr).status_code, 403)  # nor can the authority
        stranger = make_user('stranger', self.other_sqn, role=User.Role.STAFF, authority=A.CREATOR)
        self.assertEqual(self.submit(m['id'], stranger).status_code, 404)   # a stranger from another unit cannot even see it

    def test_a_pending_mission_is_locked_but_a_rejected_one_can_be_fixed_and_resubmitted(self):
        m = self.submitted_mission()
        locked = self.client_for(self.planner).patch(f"{BASE}/{m['id']}/", {'name': 'sneaky'}, format='json')
        self.assertEqual(locked.status_code, 403)
        self.client_for(self.cdr).post(f"{BASE}/{m['id']}/reject-mission/", {'comments': 'Route unsafe'}, format='json')
        fixed = self.client_for(self.planner).patch(f"{BASE}/{m['id']}/", {'name': 'Safer route'}, format='json')
        self.assertEqual(fixed.status_code, 200, fixed.data)
        again = self.submit(m['id'])
        self.assertEqual(again.status_code, 200, again.data)
        self.assertEqual(again.data['approval']['status'], 'PENDING')
        self.assertEqual(Notification.objects.filter(user=self.cdr, kind='MISSION_APPROVAL_REQUEST').count(), 2)   # one per submission


class ApprovalDecisionTests(PlanningCase):
    def test_the_selected_authority_can_approve_and_the_creator_is_notified(self):
        m = self.submitted_mission()
        self.assertTrue(self.client_for(self.cdr).get(f"{BASE}/{m['id']}/").data['can']['decide'])
        with self.captureOnCommitCallbacks(execute=True):
            res = self.client_for(self.cdr).post(f"{BASE}/{m['id']}/approve-mission/", {'comments': 'Go ahead'}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['approval']['status'], 'APPROVED')
        self.assertEqual(res.data['approval']['comments'], 'Go ahead')
        self.assertEqual(res.data['status'], 'APPROVED')
        mission = Mission.objects.get(pk=m['id'])
        self.assertEqual((mission.approval_decided_by_id, mission.status), (self.cdr.id, Mission.Status.APPROVED))
        self.assertIsNotNone(mission.approval_decided_at)
        note = Notification.objects.get(user=self.planner)
        self.assertEqual(note.kind, 'MISSION_APPROVED')
        log = MissionApprovalLog.objects.get(mission=mission, action='APPROVED')
        self.assertEqual((log.workflow, log.actor_id), ('MISSION_APPROVAL', self.cdr.id))
        self.assertTrue(AuditLog.objects.filter(object_id=str(mission.pk), action='APPROVE').exists())

    def test_rejection_requires_a_reason_and_is_communicated(self):
        m = self.submitted_mission()
        c = self.client_for(self.cdr)
        self.assertEqual(c.post(f"{BASE}/{m['id']}/reject-mission/", {}, format='json').status_code, 400)
        with self.captureOnCommitCallbacks(execute=True):
            res = c.post(f"{BASE}/{m['id']}/reject-mission/", {'comments': 'Insufficient escort'}, format='json')
        self.assertEqual(res.data['approval']['status'], 'REJECTED')
        self.assertEqual(res.data['approval']['comments'], 'Insufficient escort')
        note = Notification.objects.get(user=self.planner)
        self.assertEqual(note.kind, 'MISSION_REJECTED')
        self.assertIn('Insufficient escort', note.message)
        self.assertEqual(Mission.objects.get(pk=m['id']).status, Mission.Status.PLANNED)   # not approved

    def test_unauthorised_users_cannot_decide(self):
        m = self.submitted_mission()
        for user in (self.cdr2, self.staff_cdr, self.evaluator, self.creator, self.no_authority):
            for action in ('approve-mission', 'reject-mission'):
                res = self.client_for(user).post(f"{BASE}/{m['id']}/{action}/", {'comments': 'x'}, format='json')
                self.assertIn(res.status_code, (403, 404), (user.username, action, res.data))
        self.assertEqual(Mission.objects.get(pk=m['id']).approval_status, 'PENDING')

    def test_creator_cannot_approve_their_own_mission_even_as_a_commander(self):
        self.cdr2.mrm_authority = A.CREATOR
        self.cdr2.save()
        m = self.create(user=self.cdr2, approval_authority=str(self.cdr.id), mrm_assignee=str(self.p_mrm.id))
        self.assertEqual(self.client_for(self.cdr2).post(f'{BASE}/{m["id"]}/submit-mission/').status_code, 200)
        res = self.client_for(self.cdr2).post(f"{BASE}/{m['id']}/approve-mission/", {}, format='json')
        self.assertEqual(res.status_code, 403)
        self.assertFalse(self.client_for(self.cdr2).get(f"{BASE}/{m['id']}/").data['can']['decide'])
        # nor can the creator pick themselves as the authority
        bad = self.client_for(self.cdr2).post(f'{BASE}/', self.payload(unit=str(self.sqn.id), approval_authority=str(self.cdr2.id)), format='json')
        self.assertIn('approval_authority', bad.data)

    def test_admin_may_decide_but_not_on_their_own_mission(self):
        m = self.submitted_mission()
        self.assertEqual(self.client_for(self.admin).post(f"{BASE}/{m['id']}/approve-mission/", {}, format='json').status_code, 200)
        own = self.create(user=self.admin, approval_authority=str(self.cdr.id), mrm_assignee=str(self.p_mrm.id))
        self.client_for(self.admin).post(f"{BASE}/{own['id']}/submit-mission/")
        self.assertEqual(self.client_for(self.admin).post(f"{BASE}/{own['id']}/approve-mission/", {}, format='json').status_code, 403)

    def test_cannot_decide_twice_or_on_a_draft(self):
        m = self.submitted_mission()
        self.client_for(self.cdr).post(f"{BASE}/{m['id']}/approve-mission/", {}, format='json')
        self.assertEqual(self.client_for(self.cdr).post(f"{BASE}/{m['id']}/reject-mission/", {'comments': 'late'}, format='json').status_code, 400)
        draft = self.create(name='Another')
        self.assertEqual(self.client_for(self.admin).post(f"{BASE}/{draft['id']}/approve-mission/", {}, format='json').status_code, 400)

    def test_status_cannot_be_set_to_approved_by_hand(self):
        m = self.create()
        res = self.client_for(self.planner).patch(f"{BASE}/{m['id']}/", {'status': 'APPROVED'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.client_for(self.planner).patch(f"{BASE}/{m['id']}/", {'status': 'CANCELLED'}, format='json').status_code, 200)


class MrmWorkflowIsSeparateTests(PlanningCase):
    def mrm_payload(self, mission_id):
        return {
            'mission': mission_id, 'activity_mission': '', 'safety_objectives': 'Arrive safely', 'reviewer': str(self.evaluator.id),
            'imsafe': {k: True for k in 'IMSAFE'},
            'environment': {'weather': 'Clear skies', 'lighting': 'Daylight', 'workspace': 'Clean and organized', 'operational_tempo': 'Normal / Routine operations'},
            'hazards': [{'hazard': str(self.h_low.id)}],
        }

    def test_approving_a_mission_does_not_create_or_complete_an_mrm(self):
        m = self.submitted_mission()
        self.assertEqual(m['mrm_preparation']['status'], 'NOT_STARTED')
        res = self.client_for(self.cdr).post(f"{BASE}/{m['id']}/approve-mission/", {}, format='json')
        self.assertEqual(res.data['mrm_preparation']['status'], 'NOT_STARTED')
        self.assertFalse(Mission.objects.get(pk=m['id']).mrm_forms.exists())

    def test_the_assignee_prepares_the_mrm_and_its_status_is_tracked_independently(self):
        m = self.submitted_mission()
        detail = self.client_for(self.creator).get(f"{BASE}/{m['id']}/").data      # the MRM assignee's account can open the mission
        self.assertTrue(detail['can']['prepare_mrm'])
        create = self.client_for(self.creator).post('/api/v1/mrm/forms/', self.mrm_payload(m['id']), format='json')
        self.assertEqual(create.status_code, 201, create.data)
        self.assertEqual(create.data['activity_mission'], 'Convoy to Checkpoint 4')
        status = lambda: self.client_for(self.planner).get(f"{BASE}/{m['id']}/").data      # noqa: E731
        self.assertEqual(status()['mrm_preparation']['status'], 'IN_PROGRESS')
        self.assertEqual(status()['approval']['status'], 'PENDING')                  # mission approval untouched
        self.client_for(self.creator).post(f"/api/v1/mrm/forms/{create.data['id']}/submit/")
        self.assertEqual(status()['mrm_preparation']['status'], 'SUBMITTED')
        self.assertEqual(status()['approval']['status'], 'PENDING')
        self.client_for(self.evaluator).post(f"/api/v1/mrm/forms/{create.data['id']}/review/", {'review_status': 'approved'}, format='json')
        self.client_for(self.creator).post(f"/api/v1/mrm/forms/{create.data['id']}/approve/")
        done = status()
        self.assertEqual(done['mrm_preparation']['status'], 'APPROVED')
        self.assertEqual(done['approval']['status'], 'PENDING')                      # MRM approval never approves the mission
        self.assertEqual(Mission.objects.get(pk=m['id']).status, Mission.Status.PLANNED)

    def test_work_queue_counts(self):
        m = self.submitted_mission()
        self.assertEqual(self.client_for(self.cdr).get('/api/v1/mrm/work-queue/').data['missions_awaiting_my_approval'], 1)
        self.assertEqual(self.client_for(self.creator).get('/api/v1/mrm/work-queue/').data['mrm_to_prepare'], 1)
        self.client_for(self.cdr).post(f"{BASE}/{m['id']}/approve-mission/", {}, format='json')
        self.assertEqual(self.client_for(self.cdr).get('/api/v1/mrm/work-queue/').data['missions_awaiting_my_approval'], 0)
        self.assertEqual(self.client_for(self.creator).get('/api/v1/mrm/work-queue/').data['mrm_to_prepare'], 1)   # still to do

    def test_mrm_candidates_endpoint_lists_only_eligible_crew(self):
        m = self.create(personnel=self.crew([{'personnel': str(self.p_noacct.id), 'role': 'TEAM_MEMBER'}]))
        res = self.client_for(self.planner).get(f"{BASE}/{m['id']}/mrm-candidates/")
        self.assertEqual([p['id'] for p in res.data], [str(self.p_mrm.id)])


class VisibilityAndHistoryTests(PlanningCase):
    def test_involved_people_can_see_the_mission_and_strangers_cannot(self):
        m = self.submitted_mission(personnel=self.crew([{'personnel': str(self.p_crew_account.id), 'role': 'TEAM_MEMBER'}]))
        for user in (self.planner, self.cdr, self.creator, self.creator2):       # creator, authority, MRM assignee, crew
            self.assertEqual(self.client_for(user).get(f"{BASE}/{m['id']}/").status_code, 200, user.username)
        stranger = make_user('stranger', self.other_sqn, role=User.Role.STAFF, authority=A.CREATOR)
        self.assertEqual(self.client_for(stranger).get(f"{BASE}/{m['id']}/").status_code, 404)

    def test_the_approval_queue_filter(self):
        m = self.submitted_mission()
        res = self.client_for(self.cdr).get(f'{BASE}/?approval_status=PENDING&approval_authority={self.cdr.id}')
        self.assertEqual([x['id'] for x in res.data['results']], [m['id']])
        self.assertEqual(self.client_for(self.cdr2).get(f'{BASE}/?approval_status=PENDING&approval_authority={self.cdr2.id}').data['results'], [])

    def test_activity_history_lists_decisions_audit_and_notifications(self):
        m = self.submitted_mission()
        self.client_for(self.cdr).post(f"{BASE}/{m['id']}/reject-mission/", {'comments': 'Nope'}, format='json')
        titles = ' | '.join(e['title'] for e in self.client_for(self.planner).get(f"{BASE}/{m['id']}/activity/").data)
        for expected in ('Mission approval by authority: Submitted for Approval', 'Mission approval by authority: Rejected',
                         'Created Ground Operations mission', 'Notified'):
            self.assertIn(expected, titles)

    def test_legacy_uncategorised_missions_still_work_unchanged(self):
        legacy = Mission.objects.create(name='Old mission', unit=self.sqn)
        res = self.client_for(self.admin).patch(f'{BASE}/{legacy.id}/', {'description': 'edited'}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        detail = self.client_for(self.admin).get(f'{BASE}/{legacy.id}/').data
        self.assertEqual(detail['category_label'], 'Uncategorized (legacy)')
        self.assertEqual((detail['personnel'], detail['vehicles']), ([], []))
        listed = self.client_for(self.admin).get(f'{BASE}/').data['results']
        self.assertIn(str(legacy.id), [x['id'] for x in listed])


class DatabaseConstraintTests(PlanningCase):
    """The rules also hold if someone bypasses the API (admin site, scripts, bulk loads)."""

    def setUp(self):
        self.mission = Mission.objects.create(name='M', unit=self.sqn, category='GROUND_OPERATIONS', start_date=timezone.now(),
                                              end_date=timezone.now() + timezone.timedelta(hours=1))

    def assertRejected(self, fn):
        with self.assertRaises(IntegrityError), transaction.atomic():
            fn()

    def test_schedule_constraint(self):
        self.assertRejected(lambda: Mission.objects.create(
            name='bad', category='GROUND_OPERATIONS', start_date=timezone.now(), end_date=timezone.now() - timezone.timedelta(hours=1)))
        self.assertRejected(lambda: Mission.objects.create(name='no dates', category='GROUND_OPERATIONS'))
        Mission.objects.create(name='legacy', category='')          # uncategorised rows are exempt

    def test_one_team_leader_and_one_assignment_per_person(self):
        MissionPersonnel.objects.create(mission=self.mission, personnel=self.p_leader, role='TEAM_LEADER')
        self.assertRejected(lambda: MissionPersonnel.objects.create(mission=self.mission, personnel=self.p_member, role='TEAM_LEADER'))
        self.assertRejected(lambda: MissionPersonnel.objects.create(mission=self.mission, personnel=self.p_leader, role='DRIVER'))
        self.assertRejected(lambda: MissionPersonnel.objects.create(mission=self.mission, personnel=self.p_member, role='OTHER', role_other=''))

    def test_vehicle_is_either_fleet_or_pov(self):
        self.assertRejected(lambda: MissionVehicle.objects.create(mission=self.mission, is_pov=True, vehicle=self.truck, pov_plate_number='X1'))
        self.assertRejected(lambda: MissionVehicle.objects.create(mission=self.mission, is_pov=True, pov_plate_number=''))
        self.assertRejected(lambda: MissionVehicle.objects.create(mission=self.mission, is_pov=False, vehicle=None))
        MissionVehicle.objects.create(mission=self.mission, vehicle=self.truck, sequence=1)
        self.assertRejected(lambda: MissionVehicle.objects.create(mission=self.mission, vehicle=self.truck, sequence=2))


class NotificationApiTests(PlanningCase):
    def test_users_see_and_clear_only_their_own_notifications(self):
        self.submitted_mission()
        mine = self.client_for(self.cdr).get('/api/v1/notifications/').data['results']
        self.assertEqual(len(mine), 1)
        self.assertEqual(self.client_for(self.cdr).get('/api/v1/notifications/unread-count/').data['count'], 1)
        self.assertEqual(self.client_for(self.cdr2).get('/api/v1/notifications/').data['results'], [])
        self.assertEqual(self.client_for(self.cdr2).post(f"/api/v1/notifications/{mine[0]['id']}/read/").status_code, 404)
        self.assertTrue(self.client_for(self.cdr).post(f"/api/v1/notifications/{mine[0]['id']}/read/").data['is_read'])
        self.assertEqual(self.client_for(self.cdr).get('/api/v1/notifications/unread-count/').data['count'], 0)
        self.assertEqual(self.client_for(self.creator).post('/api/v1/notifications/read-all/').data['updated'], 1)

    def test_duplicate_delivery_is_suppressed_by_the_dedupe_key(self):
        from apps.core.notifications import notify
        with self.captureOnCommitCallbacks(execute=True):
            for _ in range(3):
                notify([self.cdr], 'GENERAL', 'hello', dedupe_key='once')
        self.assertEqual(Notification.objects.filter(user=self.cdr, dedupe_key='once').count(), 1)


class ColumnLimitTests(PlanningCase):
    """PostgreSQL enforces varchar lengths (SQLite does not): everything the planner writes must fit its column."""

    def test_worst_case_values_fit_every_column(self):
        from django.core.exceptions import ValidationError as DjangoValidationError
        big_leg = self.leg(origin={'name': 'O' * 200, 'lat': 8.48, 'lng': 124.64}, destination={'name': 'D' * 200, 'lat': 8.5, 'lng': 124.7},
                           stops=[{'name': 'S' * 200, 'lat': 8.49, 'lng': 124.66, 'notes': 'n' * 500}])
        m = self.create(name='N' * 200, vehicles=[
            {'is_pov': True, 'pov': {'plate_number': 'P' * 20, 'vehicle_type': 'T' * 100, 'make': 'M' * 100, 'model': 'X' * 100,
                                    'color': 'C' * 50, 'owner_name': 'W' * 150, 'description': 'd' * 1000}, 'itinerary': [big_leg]}],
            personnel=self.crew([{'personnel': str(self.p_noacct.id), 'role': 'OTHER', 'role_other': 'R' * 100}]))
        mission = Mission.objects.get(pk=m['id'])
        rows = [mission, *mission.personnel_assignments.all(), *mission.vehicle_assignments.all()]
        for mv in mission.vehicle_assignments.all():
            for leg in mv.itinerary.all():
                rows += [leg, *leg.stops.all()]
        for obj in rows:
            try:
                obj.full_clean(exclude=['origin_location', 'destination_location', 'location', 'client_request_id'], validate_unique=False,
                               validate_constraints=False)
            except DjangoValidationError as exc:
                self.fail(f'{type(obj).__name__} violates a PostgreSQL column limit: {exc}')

    def test_values_over_the_limit_are_rejected_with_a_message_not_a_database_error(self):
        res = self.client_for(self.planner).post(f'{BASE}/', self.payload(name='N' * 201), format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('name', res.data)
        res = self.client_for(self.planner).post(f'{BASE}/', self.payload(vehicles=[{'is_pov': True, 'pov': {'plate_number': 'P' * 21, 'vehicle_type': 'Car'}}]), format='json')
        self.assertIn('vehicles[0].pov.plate_number', res.data)
        res = self.client_for(self.planner).post(f'{BASE}/', self.payload(personnel=self.crew([{'personnel': str(self.p_noacct.id), 'role': 'OTHER', 'role_other': 'R' * 101}])), format='json')
        self.assertIn('personnel[4].role_other', res.data)


class PersonnelPickerTests(PlanningCase):
    def test_personnel_list_tells_the_picker_who_can_prepare_an_mrm(self):
        res = self.client_for(self.planner).get('/api/v1/personnel/records/?page_size=50')
        self.assertEqual(res.status_code, 200, res.data)
        by_sn = {p['service_number']: p for p in res.data['results']}
        self.assertTrue(by_sn['SN-4']['mrm_ready'])        # linked to an MRM Creator account
        self.assertFalse(by_sn['SN-5']['mrm_ready'])       # no account
        self.assertFalse(by_sn['SN-5']['has_account'])
        self.assertTrue(by_sn['SN-4']['has_account'])
