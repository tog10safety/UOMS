import assert from 'node:assert/strict';
import { test } from 'node:test';

import { clearError, errorsFromAxios, firstErrorKey, flattenApiErrors } from './formErrors.ts';
import { validateMrmDraft } from './mrmValidation.ts';

const base = {
  activity: 'Resupply', objectives: 'Be safe', reviewer: 'ev-1', evaluatorIds: ['ev-1', 'ev-2'], reviewerLocked: false,
  imsafe: { I: true, M: true, S: true, A: true, F: true, E: true },
  env: { weather: 'Clear skies', lighting: 'Daylight', workspace: 'None', operational_tempo: 'Normal' },
  hazardCount: 1, needsUnit: false, unit: null as string | null,
};

test('a complete draft with a selected evaluator has no errors (the reported bug)', () => {
  assert.deepEqual(validateMrmDraft(base), {});
});

test('a missing evaluator is reported on the evaluator field only', () => {
  const e = validateMrmDraft({ ...base, reviewer: null });
  assert.deepEqual(Object.keys(e), ['reviewer']);
  assert.match(e.reviewer, /Select an evaluator/);
});

test('an evaluator id that is no longer offered is reported as invalid, not as missing', () => {
  const e = validateMrmDraft({ ...base, reviewer: 'gone' });
  assert.match(e.reviewer, /no longer available/);
});

test('no evaluators available gives an explanatory message', () => {
  const e = validateMrmDraft({ ...base, reviewer: null, evaluatorIds: [] });
  assert.match(e.reviewer, /No evaluator is available/);
});

test('a locked reviewer is never demanded from the user', () => {
  assert.deepEqual(validateMrmDraft({ ...base, reviewer: null, reviewerLocked: true }), {});
});

test('other problems do not touch the evaluator selection', () => {
  const e = validateMrmDraft({ ...base, activity: '', hazardCount: 0 });
  assert.ok(e.activity_mission && e.hazards);
  assert.equal(e.reviewer, undefined);
});

test('admin must choose a unit first', () => {
  assert.ok(validateMrmDraft({ ...base, needsUnit: true, unit: null }).unit);
  assert.equal(validateMrmDraft({ ...base, needsUnit: true, unit: 'u1' }).unit, undefined);
});

test('DRF field errors map to their fields', () => {
  const e = flattenApiErrors({ reviewer: ['Please select an evaluator to review this MRM.'], hazards: 'x', detail: 'General problem' });
  assert.equal(e.reviewer, 'Please select an evaluator to review this MRM.');
  assert.equal(e.hazards, 'x');
  assert.equal(e._general, 'General problem');
});

test('nested list-index paths from the mission API are preserved', () => {
  const e = flattenApiErrors({ 'vehicles[0].itinerary[1].origin.mgrs': ['bad mgrs'], personnel: ['Assign exactly one Team Leader.'] });
  assert.equal(e['vehicles[0].itinerary[1].origin.mgrs'], 'bad mgrs');
  assert.equal(e.personnel, 'Assign exactly one Team Leader.');
});

test('nested objects flatten with dotted keys', () => {
  assert.equal(flattenApiErrors({ environment: { weather: ['required'] } })['environment.weather'], 'required');
});

test('axios errors, strings and empty responses all produce a message', () => {
  assert.equal(errorsFromAxios({ response: { data: { reviewer: ['bad'] } } }).reviewer, 'bad');
  assert.equal(errorsFromAxios({ response: { data: 'Server exploded' } })._general, 'Server exploded');
  assert.match(errorsFromAxios(new Error('network'))._general, /try again/);
});

test('first error key follows the form order, general errors last', () => {
  assert.equal(firstErrorKey({ hazards: 'x', reviewer: 'y' }, ['reviewer', 'hazards']), 'reviewer');
  assert.equal(firstErrorKey({ _general: 'g' }), '_general');
});

test('clearing one field leaves the others', () => {
  assert.deepEqual(clearError({ a: '1', b: '2' }, 'a'), { b: '2' });
  const same = { a: '1' };
  assert.equal(clearError(same, 'zzz'), same);
});
