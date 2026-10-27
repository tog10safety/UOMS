import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  buildGroundPayload, emptyGroundForm, emptyLeg, emptyStop, emptyVehicle, mgrsLooksValid, moveItem, newKey, removeAt,
  hydrateGroundForm, toLocalInput, validateGroundForm, validateVehicle, type GroundForm, type PersonInput, type VehicleInput,
} from './missionForm.ts';

const person = (id: string, role: string, extra: Partial<PersonInput> = {}): PersonInput => (
  { key: newKey(), personnel: id, label: `Person ${id}`, sublabel: '', role, role_other: '', mrmReady: false, ...extra });

const valid = (): GroundForm => ({
  ...emptyGroundForm(), name: 'Convoy', start_date: '2026-11-01T06:00', end_date: '2026-11-01T18:00', unit: 'u1', responsible_section: 's1',
  personnel: [person('p1', 'TEAM_LEADER'), person('p2', 'TEAM_MEMBER')],
});

const place = (name: string, lat = '8.48', lng = '124.64') => ({ name, lat, lng, mgrs: '' });

test('a complete form has no errors', () => assert.deepEqual(validateGroundForm(valid()), {}));

test('all required fields are reported', () => {
  const e = validateGroundForm(emptyGroundForm());
  for (const k of ['name', 'start_date', 'end_date', 'unit', 'responsible_section', 'personnel']) assert.ok(e[k], k);
});

test('estimated end may equal but not precede the start', () => {
  assert.equal(validateGroundForm({ ...valid(), end_date: '2026-11-01T06:00' }).end_date, undefined);
  assert.match(validateGroundForm({ ...valid(), end_date: '2026-11-01T05:59' }).end_date, /earlier/);
});

test('the section must belong to the chosen unit', () => {
  assert.match(validateGroundForm(valid(), { sectionUnitId: 'other' }).responsible_section, /does not belong/);
  assert.equal(validateGroundForm(valid(), { sectionUnitId: 'u1' }).responsible_section, undefined);
});

test('exactly one team leader; duplicates and OTHER need explanation', () => {
  assert.match(validateGroundForm({ ...valid(), personnel: [person('p1', 'TEAM_MEMBER')] }).personnel, /exactly one Team Leader/);
  assert.match(validateGroundForm({ ...valid(), personnel: [person('p1', 'TEAM_LEADER'), person('p2', 'TEAM_LEADER')] }).personnel, /Only one/);
  assert.ok(validateGroundForm({ ...valid(), personnel: [...valid().personnel, person('p1', 'DRIVER')] })['personnel[2].personnel']);
  assert.ok(validateGroundForm({ ...valid(), personnel: [...valid().personnel, person('p3', 'OTHER')] })['personnel[2].role_other']);
  assert.equal(validateGroundForm({ ...valid(), personnel: [...valid().personnel, person('p3', 'OTHER', { role_other: 'Medic' })] })['personnel[2].role_other'], undefined);
});

test('authority and MRM assignee are only mandatory when submitting', () => {
  assert.equal(validateGroundForm(valid()).approval_authority, undefined);
  const e = validateGroundForm(valid(), { forSubmit: true });
  assert.ok(e.approval_authority && e.mrm_assignee);
  assert.deepEqual(validateGroundForm({ ...valid(), approval_authority: 'a1', mrm_assignee: 'p2' }, { forSubmit: true }), {});
});

test('the MRM assignee must be one of the assigned personnel', () => {
  assert.match(validateGroundForm({ ...valid(), mrm_assignee: 'stranger' }).mrm_assignee, /assigned to this mission/);
});

test('no vehicle is perfectly valid; each vehicle may have no itinerary', () => {
  assert.deepEqual(validateGroundForm(valid()), {});
  const v: VehicleInput = { ...emptyVehicle(), vehicle: 'veh1', vehicleLabel: 'SAA 111' };
  assert.deepEqual(validateGroundForm({ ...valid(), vehicles: [v] }), {});
});

test('fleet vehicle must be chosen; duplicates are caught', () => {
  assert.ok(validateGroundForm({ ...valid(), vehicles: [emptyVehicle()] })['vehicles[0].vehicle']);
  const a: VehicleInput = { ...emptyVehicle(), vehicle: 'v1', vehicleLabel: 'SAA 111' };
  assert.match(validateGroundForm({ ...valid(), vehicles: [a, { ...a, key: newKey() }] })['vehicles[1].vehicle'], /already on this mission/);
});

test('POV needs plate and type but never an odometer or a fleet vehicle', () => {
  const pov = emptyVehicle(true);
  const e = validateVehicle(pov, 0, new Set());
  assert.ok(e['vehicles[0].pov.plate_number'] && e['vehicles[0].pov.vehicle_type']);
  assert.equal(e['vehicles[0].vehicle'], undefined);
  pov.pov.plate_number = 'abc 123'; pov.pov.vehicle_type = 'Sedan';
  assert.deepEqual(validateVehicle(pov, 0, new Set()), {});
  const payload = buildGroundPayload({ ...valid(), vehicles: [pov] });
  assert.equal(payload.vehicles[0].vehicle, null);
  assert.equal(JSON.stringify(payload).includes('odometer'), false);
  const two = validateGroundForm({ ...valid(), vehicles: [pov, { ...pov, key: newKey() }] });
  assert.match(two['vehicles[1].pov.plate_number'], /already on this mission/);
});

test('driver must be on the crew', () => {
  const v: VehicleInput = { ...emptyVehicle(), vehicle: 'v1', driver: 'nobody' };
  assert.ok(validateGroundForm({ ...valid(), vehicles: [v] })['vehicles[0].driver']);
});

test('itinerary: places need a name and either map coordinates or a well-formed MGRS', () => {
  const leg = { ...emptyLeg(), origin: place('Camp'), destination: { name: 'HQ', lat: '', lng: '', mgrs: '51P XQ 81324 37990' } };
  const v: VehicleInput = { ...emptyVehicle(), vehicle: 'v1', itinerary: [leg] };
  assert.deepEqual(validateVehicle(v, 0, new Set()), {});

  const bad: VehicleInput = { ...v, itinerary: [{ ...leg, origin: { name: '', lat: '', lng: '', mgrs: '' }, destination: { name: 'HQ', lat: '', lng: '', mgrs: 'garbage' } }] };
  const e = validateVehicle(bad, 0, new Set());
  assert.ok(e['vehicles[0].itinerary[0].origin.name'] && e['vehicles[0].itinerary[0].origin.location']);
  assert.match(e['vehicles[0].itinerary[0].destination.mgrs'], /not a valid MGRS/);
});

test('coordinate range and half-entered coordinates are caught', () => {
  const mk = (origin: ReturnType<typeof place>) => ({ ...emptyVehicle(), vehicle: 'v1', itinerary: [{ ...emptyLeg(), origin, destination: place('B') }] });
  assert.ok(validateVehicle(mk(place('A', '91', '0')), 0, new Set())['vehicles[0].itinerary[0].origin.location']);
  assert.ok(validateVehicle(mk({ name: 'A', lat: '8.4', lng: '', mgrs: '' }), 0, new Set())['vehicles[0].itinerary[0].origin.location']);
});

test('intermediate stops are validated and arrival may not precede departure', () => {
  const leg = { ...emptyLeg(), origin: place('A'), destination: place('B'), stops: [{ ...emptyStop(), name: '' }],
    planned_departure: '2026-11-01T10:00', planned_arrival: '2026-11-01T09:00' };
  const e = validateVehicle({ ...emptyVehicle(), vehicle: 'v1', itinerary: [leg] }, 0, new Set());
  assert.ok(e['vehicles[0].itinerary[0].stops[0].name']);
  assert.match(e['vehicles[0].itinerary[0].planned_arrival'], /earlier than departure/);
});

test('MGRS shape check accepts spaced, compact and coarse references and rejects nonsense', () => {
  for (const ok of ['51P XQ 81324 37990', '51PXQ8132437990', '51p xq 813 379', '4Q FJ 12 67']) assert.ok(mgrsLooksValid(ok), ok);
  for (const bad of ['', 'hello', '51P XQ 123 45', '99 XQ', '51I XQ 1 1', '51P XQ 8132437990 1']) assert.equal(mgrsLooksValid(bad), false, bad);
});

test('reordering and removing never mutate the original list', () => {
  const list = ['a', 'b', 'c'];
  assert.deepEqual(moveItem(list, 0, 2), ['b', 'c', 'a']);
  assert.deepEqual(moveItem(list, 2, 0), ['c', 'a', 'b']);
  assert.equal(moveItem(list, 0, 9), list);
  assert.deepEqual(removeAt(list, 1), ['a', 'c']);
  assert.deepEqual(list, ['a', 'b', 'c']);
});

test('payload carries ids, structured roles, ISO times and omits empty MGRS', () => {
  const f: GroundForm = { ...valid(), approval_authority: 'a1', mrm_assignee: 'p2',
    vehicles: [{ ...emptyVehicle(), vehicle: 'v1', driver: 'p2', itinerary: [{ ...emptyLeg(), origin: place('Camp', '8.5', '124.6'), destination: place('HQ'), stops: [{ ...emptyStop(), ...place('Bridge') }] }] }] };
  const p = buildGroundPayload(f, 'tok-1');
  assert.equal(p.category, 'GROUND_OPERATIONS');
  assert.equal(p.client_request_id, 'tok-1');
  assert.deepEqual(p.personnel[0], { personnel: 'p1', role: 'TEAM_LEADER', role_other: '' });
  assert.match(p.start_date as string, /^2026-11-01T\d\d:\d\d:00\.000Z$/);
  assert.equal(p.vehicles[0].itinerary[0].origin.mgrs, undefined);
  assert.equal(p.vehicles[0].itinerary[0].origin.lat, 8.5);
  assert.equal(p.vehicles[0].itinerary[0].stops[0].name, 'Bridge');
  assert.equal(p.approval_authority, 'a1');
});

test('role_other is dropped unless the role is OTHER', () => {
  const f = { ...valid(), personnel: [person('p1', 'TEAM_LEADER', { role_other: 'leftover' }), person('p2', 'OTHER', { role_other: ' Medic ' })] };
  const p = buildGroundPayload(f);
  assert.equal(p.personnel[0].role_other, '');
  assert.equal(p.personnel[1].role_other, 'Medic');
});

test('datetime-local conversion round-trips', () => {
  assert.equal(toLocalInput(null), '');
  const local = toLocalInput('2026-11-01T06:00:00Z');
  assert.match(local, /^2026-1[01]-\d\dT\d\d:\d\d$/);
  assert.equal(new Date(local).toISOString(), '2026-11-01T06:00:00.000Z');
});


test('saved missions hydrate into a form that validates and re-serialises to the same data (edit round trip)', () => {
  const plan = {
    name: 'Convoy', description: 'd', start_date: '2026-11-01T06:00:00Z', end_date: '2026-11-01T18:00:00Z', unit: 'u1', responsible_section: 's1',
    personnel: [
      { id: 'a1', personnel: 'p1', role: 'TEAM_LEADER', role_other: '', role_label: 'Team Leader', person: { id: 'p1', name: 'Juan Cruz', service_number: 'SN-1', rank: 'SGT', unit: 'S101', has_account: false } },
      { id: 'a2', personnel: 'p2', role: 'OTHER', role_other: 'Medic', role_label: 'Medic', person: { id: 'p2', name: 'Ana Reyes', service_number: 'SN-2', rank: 'CPL', unit: 'S101', has_account: true } },
    ],
    vehicles: [{
      id: 'v1', is_pov: false, sequence: 1, vehicle: 'veh1', fleet: { plate_number: 'SAA 111', vehicle_type: 'Truck', make: 'Isuzu', model: 'Elf' }, pov: null,
      driver: 'p2', driver_name: 'Ana Reyes', notes: 'n',
      itinerary: [{ id: 'l1', sequence: 1, origin: { name: 'Camp', lat: 8.4822, lng: 124.6472, mgrs: '51P XQ 81324 37990' },
        destination: { name: 'HQ', lat: 8.51, lng: 124.7, mgrs: '51P XQ 87000 40000' },
        stops: [{ sequence: 1, name: 'Bridge', lat: 8.495, lng: 124.67, mgrs: '51P XQ 84000 39000', notes: 'fuel' }],
        planned_departure: '2026-11-01T07:00:00Z', planned_arrival: null, notes: '' }],
    }, {
      id: 'v2', is_pov: true, sequence: 2, vehicle: null, fleet: null,
      pov: { plate_number: 'POV 1', vehicle_type: 'Sedan', make: 'Honda', model: 'Civic', color: '', owner_name: '', description: '' },
      driver: null, driver_name: null, notes: '', itinerary: [],
    }],
    approval: { authority: { id: 'auth1' } }, mrm_assignee: { id: 'p2' },
    category: 'GROUND_OPERATIONS',
  } as unknown as Parameters<typeof hydrateGroundForm>[0];

  const form = hydrateGroundForm(plan, new Set(['p2']));
  assert.deepEqual(validateGroundForm(form, { forSubmit: true }), {});
  assert.equal(form.personnel[1].mrmReady, true);
  assert.equal(form.vehicles[0].vehicleLabel, 'SAA 111 — Truck · Isuzu · Elf');
  assert.equal(form.vehicles[0].itinerary[0].stops[0].name, 'Bridge');
  assert.equal(form.vehicles[1].pov.plate_number, 'POV 1');
  const payload = buildGroundPayload(form);
  assert.equal(payload.vehicles[0].itinerary[0].origin.lat, 8.4822);
  assert.equal(payload.vehicles[0].itinerary[0].origin.mgrs, '51P XQ 81324 37990');
  assert.equal(payload.vehicles[1].vehicle, null);
  assert.equal(payload.approval_authority, 'auth1');
  assert.equal(payload.personnel[1].role_other, 'Medic');
  assert.equal(payload.vehicles[0].itinerary[0].planned_arrival, null);
});
