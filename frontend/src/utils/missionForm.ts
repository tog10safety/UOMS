/**
 * Pure logic behind the Ground Operations mission form: the form's state shape, the payload sent to the API, a
 * client-side validator that mirrors the server rules (error keys use the SAME paths the API returns, e.g.
 * "vehicles[0].itinerary[1].origin.mgrs"), and small list helpers. No React in here so it can be unit-tested.
 */
import type { FieldErrors } from './formErrors';

export const ROLE_TEAM_LEADER = 'TEAM_LEADER';
export const ROLE_OTHER = 'OTHER';

export interface PlaceInput { name: string; lat: string; lng: string; mgrs: string }
export interface StopInput extends PlaceInput { notes: string }
export interface LegInput {
  origin: PlaceInput; destination: PlaceInput; stops: StopInput[]; planned_departure: string; planned_arrival: string; notes: string;
}
export interface PovInput { plate_number: string; vehicle_type: string; make: string; model: string; color: string; owner_name: string; description: string }
export interface VehicleInput {
  key: string; is_pov: boolean; vehicle: string | null; vehicleLabel: string; pov: PovInput; driver: string | null; notes: string; itinerary: LegInput[];
}
export interface PersonInput { key: string; personnel: string; label: string; sublabel: string; role: string; role_other: string; mrmReady: boolean }

export interface GroundForm {
  name: string; description: string; start_date: string; end_date: string;
  unit: string | null; responsible_section: string | null;
  personnel: PersonInput[]; vehicles: VehicleInput[];
  approval_authority: string | null; mrm_assignee: string | null;
}

let counter = 0;
export const newKey = () => `k${Date.now().toString(36)}${(counter++).toString(36)}`;

export const emptyPlace = (): PlaceInput => ({ name: '', lat: '', lng: '', mgrs: '' });
export const emptyStop = (): StopInput => ({ ...emptyPlace(), notes: '' });
export const emptyLeg = (): LegInput => ({ origin: emptyPlace(), destination: emptyPlace(), stops: [], planned_departure: '', planned_arrival: '', notes: '' });
export const emptyPov = (): PovInput => ({ plate_number: '', vehicle_type: '', make: '', model: '', color: '', owner_name: '', description: '' });
export const emptyVehicle = (isPov = false): VehicleInput => ({
  key: newKey(), is_pov: isPov, vehicle: null, vehicleLabel: '', pov: emptyPov(), driver: null, notes: '', itinerary: [],
});
export const emptyGroundForm = (): GroundForm => ({
  name: '', description: '', start_date: '', end_date: '', unit: null, responsible_section: null,
  personnel: [], vehicles: [], approval_authority: null, mrm_assignee: null,
});

// --- generic list helpers (used for reordering legs, stops and vehicles) -------------------------------------
export function moveItem<T>(list: T[], from: number, to: number): T[] {
  if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) return list;
  const next = list.slice();
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}
export const removeAt = <T,>(list: T[], index: number): T[] => list.filter((_, i) => i !== index);
export const replaceAt = <T,>(list: T[], index: number, value: T): T[] => list.map((v, i) => (i === index ? value : v));

// --- coordinates ---------------------------------------------------------------------------------------------
export const hasCoords = (p: PlaceInput) => p.lat.trim() !== '' && p.lng.trim() !== '' && !Number.isNaN(Number(p.lat)) && !Number.isNaN(Number(p.lng));
export function coordsInRange(p: PlaceInput): boolean {
  if (!hasCoords(p)) return false;
  const lat = Number(p.lat), lng = Number(p.lng);
  return lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180;
}

/** Loose MGRS shape check (zone+band, two 100 km letters, even digit run). The server does the authoritative parse. */
const MGRS_SHAPE = /^\s*\d{1,2}\s*[C-HJ-NP-X]\s*[A-HJ-NP-Z][A-HJ-NP-V]\s*(?:\d\s*){0,10}$/i;
export function mgrsLooksValid(text: string): boolean {
  const t = text.trim();
  if (!t || !MGRS_SHAPE.test(t)) return false;
  const digits = t.replace(/[^0-9]/g, '').slice(/^\d{1,2}/.exec(t)![0].length);
  return digits.length % 2 === 0;
}

// --- validation (mirrors apps/missions/ground.py) -------------------------------------------------------------
function validatePlace(p: PlaceInput, path: string, label: string, e: FieldErrors) {
  if (!p.name.trim()) e[`${path}.name`] = `${label} name is required.`;
  if (hasCoords(p) && !coordsInRange(p)) e[`${path}.location`] = `${label}: latitude must be -90…90 and longitude -180…180.`;
  else if (!hasCoords(p) && (p.lat.trim() || p.lng.trim())) e[`${path}.location`] = `${label}: latitude and longitude must both be numbers.`;
  else if (!hasCoords(p)) {
    if (!p.mgrs.trim()) e[`${path}.location`] = `${label}: choose a point on the map or enter an MGRS reference.`;
    else if (!mgrsLooksValid(p.mgrs)) e[`${path}.mgrs`] = `${label}: "${p.mgrs.trim()}" is not a valid MGRS reference (e.g. 51P XQ 81324 37990).`;
  } else if (p.mgrs.trim() && !mgrsLooksValid(p.mgrs)) e[`${path}.mgrs`] = `${label}: "${p.mgrs.trim()}" is not a valid MGRS reference.`;
}

export function validateVehicle(v: VehicleInput, index: number, personIds: Set<string>, e: FieldErrors = {}): FieldErrors {
  const path = `vehicles[${index}]`;
  if (v.is_pov) {
    if (!v.pov.plate_number.trim()) e[`${path}.pov.plate_number`] = 'Plate number is required for a privately owned vehicle.';
    if (!v.pov.vehicle_type.trim()) e[`${path}.pov.vehicle_type`] = 'Vehicle type is required.';
  } else if (!v.vehicle) e[`${path}.vehicle`] = 'Select a vehicle from the Vehicle Inventory (or add a POV).';
  if (v.driver && !personIds.has(v.driver)) e[`${path}.driver`] = 'The driver must be one of the personnel assigned to this mission.';
  v.itinerary.forEach((leg, j) => {
    const lp = `${path}.itinerary[${j}]`;
    validatePlace(leg.origin, `${lp}.origin`, 'Origin', e);
    validatePlace(leg.destination, `${lp}.destination`, 'Destination', e);
    leg.stops.forEach((s, k) => validatePlace(s, `${lp}.stops[${k}]`, `Stop ${k + 1}`, e));
    if (leg.planned_departure && leg.planned_arrival && new Date(leg.planned_arrival) < new Date(leg.planned_departure)) {
      e[`${lp}.planned_arrival`] = 'Arrival cannot be earlier than departure.';
    }
  });
  return e;
}

export function validateGroundForm(f: GroundForm, opts: { forSubmit?: boolean; sectionUnitId?: string | null } = {}): FieldErrors {
  const e: FieldErrors = {};
  if (!f.name.trim()) e.name = 'Mission/Activity is required.';
  else if (f.name.length > 200) e.name = 'Mission/Activity must be 200 characters or fewer.';
  if (!f.start_date) e.start_date = 'Estimated start is required.';
  if (!f.end_date) e.end_date = 'Estimated end is required.';
  if (f.start_date && f.end_date && new Date(f.end_date) < new Date(f.start_date)) e.end_date = 'Estimated end cannot be earlier than the estimated start.';
  if (!f.unit) e.unit = 'Unit Primary Responsible (UPR) is required.';
  if (!f.responsible_section) e.responsible_section = 'Office/Section Primary Responsible (O/SPR) is required.';
  else if (f.unit && opts.sectionUnitId && opts.sectionUnitId !== f.unit) e.responsible_section = 'That office/section does not belong to the selected unit.';

  if (f.personnel.length === 0) e.personnel = 'Assign at least one person to the mission.';
  const seen = new Set<string>();
  let leaders = 0;
  f.personnel.forEach((p, i) => {
    if (seen.has(p.personnel)) e[`personnel[${i}].personnel`] = `${p.label} is already assigned to this mission.`;
    seen.add(p.personnel);
    if (!p.role) e[`personnel[${i}].role`] = 'Choose a role for this person.';
    if (p.role === ROLE_OTHER && !p.role_other.trim()) e[`personnel[${i}].role_other`] = 'Describe the role.';
    if (p.role === ROLE_TEAM_LEADER) leaders += 1;
  });
  if (f.personnel.length && leaders === 0) e.personnel = 'Assign exactly one Team Leader.';
  if (leaders > 1) e.personnel = 'Only one person can be the Team Leader.';

  const personIds = new Set(f.personnel.map((p) => p.personnel));
  const fleet = new Set<string>(), povs = new Set<string>();
  f.vehicles.forEach((v, i) => {
    validateVehicle(v, i, personIds, e);
    if (!v.is_pov && v.vehicle) {
      if (fleet.has(v.vehicle)) e[`vehicles[${i}].vehicle`] = `${v.vehicleLabel || 'This vehicle'} is already on this mission.`;
      fleet.add(v.vehicle);
    }
    if (v.is_pov && v.pov.plate_number.trim()) {
      const plate = v.pov.plate_number.trim().toUpperCase();
      if (povs.has(plate)) e[`vehicles[${i}].pov.plate_number`] = `POV ${plate} is already on this mission.`;
      povs.add(plate);
    }
  });

  if (f.mrm_assignee && !personIds.has(f.mrm_assignee)) e.mrm_assignee = 'The MRM assignee must be one of the personnel assigned to this mission.';
  if (opts.forSubmit) {
    if (!f.approval_authority) e.approval_authority = 'Select the approving authority before submitting.';
    if (!f.mrm_assignee) e.mrm_assignee = 'Select who will prepare the Mission Risk Management (MRM) form.';
  }
  return e;
}

// --- payload -------------------------------------------------------------------------------------------------
const num = (s: string) => (s.trim() === '' ? undefined : Number(s));
const placeOut = (p: PlaceInput) => ({ name: p.name.trim(), lat: num(p.lat), lng: num(p.lng), mgrs: p.mgrs.trim() || undefined });
const iso = (local: string) => (local ? new Date(local).toISOString() : null);

export function buildGroundPayload(f: GroundForm, clientRequestId?: string) {
  return {
    category: 'GROUND_OPERATIONS',
    ...(clientRequestId ? { client_request_id: clientRequestId } : {}),
    name: f.name.trim(), description: f.description.trim(),
    start_date: iso(f.start_date), end_date: iso(f.end_date),
    unit: f.unit, responsible_section: f.responsible_section,
    personnel: f.personnel.map((p) => ({ personnel: p.personnel, role: p.role, role_other: p.role === ROLE_OTHER ? p.role_other.trim() : '' })),
    vehicles: f.vehicles.map((v) => ({
      is_pov: v.is_pov, vehicle: v.is_pov ? null : v.vehicle, pov: v.is_pov ? v.pov : null, driver: v.driver, notes: v.notes.trim(),
      itinerary: v.itinerary.map((leg) => ({
        origin: placeOut(leg.origin), destination: placeOut(leg.destination),
        stops: leg.stops.map((s) => ({ ...placeOut(s), notes: s.notes.trim() })),
        planned_departure: iso(leg.planned_departure), planned_arrival: iso(leg.planned_arrival), notes: leg.notes.trim(),
      })),
    })),
    approval_authority: f.approval_authority, mrm_assignee: f.mrm_assignee,
  };
}

/** ISO string -> value for <input type="datetime-local"> in the user's timezone. */
export function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}


// --- hydrate an existing mission back into form state (edit mode) ------------------------------------------------
import type { MissionPlanning, PlanLeg, PlanVehicle, PlaceOut } from '../types/missionOps';

const placeIn = (p: PlaceOut): PlaceInput => ({ name: p.name, lat: String(p.lat), lng: String(p.lng), mgrs: p.mgrs });
const legIn = (leg: PlanLeg): LegInput => ({
  origin: placeIn(leg.origin), destination: placeIn(leg.destination),
  stops: leg.stops.map((s) => ({ ...placeIn(s), notes: s.notes })),
  planned_departure: toLocalInput(leg.planned_departure), planned_arrival: toLocalInput(leg.planned_arrival), notes: leg.notes,
});
const vehicleIn = (v: PlanVehicle): VehicleInput => ({
  key: v.id, is_pov: v.is_pov, vehicle: v.vehicle,
  vehicleLabel: v.fleet ? `${v.fleet.plate_number} — ${[v.fleet.vehicle_type, v.fleet.make, v.fleet.model].filter(Boolean).join(' · ')}` : '',
  pov: v.pov ? { ...v.pov } : emptyPov(), driver: v.driver, notes: v.notes, itinerary: v.itinerary.map(legIn),
});

export function hydrateGroundForm(
  plan: MissionPlanning & { name: string; description: string; start_date: string | null; end_date: string | null; unit: string | null },
  mrmReadyIds: Set<string> = new Set(),
): GroundForm {
  return {
    name: plan.name, description: plan.description ?? '', start_date: toLocalInput(plan.start_date), end_date: toLocalInput(plan.end_date),
    unit: plan.unit, responsible_section: plan.responsible_section ?? null,
    personnel: plan.personnel.map((a) => ({
      key: a.id, personnel: a.personnel, label: `${a.person.rank} ${a.person.name}`.trim(), sublabel: `${a.person.service_number} · ${a.person.unit ?? ''}`,
      role: a.role, role_other: a.role_other, mrmReady: mrmReadyIds.has(a.personnel),
    })),
    vehicles: plan.vehicles.map(vehicleIn),
    approval_authority: plan.approval.authority?.id ?? null,
    mrm_assignee: plan.mrm_assignee?.id ?? null,
  };
}
