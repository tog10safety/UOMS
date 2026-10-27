import type { FieldDef } from '@/components/common/RecordForm';
import type { LatLng, PersonnelListItem, Unit } from '@/types';

export const MISSION_STATUS_OPTIONS = [
  { value: 'PLANNED', label: 'Planned' },
  { value: 'APPROVED', label: 'Approved' },
  { value: 'ONGOING', label: 'Ongoing' },
  { value: 'COMPLETED', label: 'Completed' },
  { value: 'CANCELLED', label: 'Cancelled' },
].map((o) => ({ ...o }));

export function buildMissionFields(units: Unit[], personnel: PersonnelListItem[]): FieldDef[] {
  return [
    { name: 'name', label: 'Mission Name', type: 'text', required: true, span: 2 },
    { name: 'description', label: 'Description', type: 'textarea' },
    { name: 'unit', label: 'Owning Unit / AOR', type: 'search', options: units.map((u) => ({ value: u.id, label: u.name, sublabel: u.code })) },
    { name: 'mission_commander', label: 'Mission Commander', type: 'search', options: personnel.map((p) => ({ value: p.id, label: p.full_name, sublabel: p.service_number })) },
    { name: 'status', label: 'Status', type: 'select', required: true, defaultValue: 'PLANNED', options: MISSION_STATUS_OPTIONS },
    { name: 'start_date', label: 'Start', type: 'datetime' },
    { name: 'end_date', label: 'End', type: 'datetime' },
    {
      name: 'location', label: 'Mission Location', type: 'latlng', payloadKey: 'location_input',
      getInitial: (r: { location: LatLng | null }) => ({ lat: r.location ? String(r.location.lat) : '', lng: r.location ? String(r.location.lng) : '' }),
    },
  ];
}

export const HAZARD_CATEGORY_OPTIONS = [
  { value: 'WEATHER', label: 'Weather / Environmental' },
  { value: 'MECHANICAL', label: 'Mechanical / Equipment Failure' },
  { value: 'HUMAN_ERROR', label: 'Human Error' },
  { value: 'ENEMY_ACTION', label: 'Enemy / Hostile Action' },
  { value: 'TERRAIN', label: 'Terrain / Route' },
  { value: 'MEDICAL', label: 'Medical' },
  { value: 'OTHER', label: 'Other' },
];

export const PROBABILITY_OPTIONS = [
  { value: 'FREQUENT', label: 'Frequent (A)' },
  { value: 'LIKELY', label: 'Likely (B)' },
  { value: 'OCCASIONAL', label: 'Occasional (C)' },
  { value: 'SELDOM', label: 'Seldom (D)' },
  { value: 'UNLIKELY', label: 'Unlikely (E)' },
];

export const SEVERITY_OPTIONS = [
  { value: 'CATASTROPHIC', label: 'Catastrophic (I)' },
  { value: 'CRITICAL', label: 'Critical (II)' },
  { value: 'MODERATE', label: 'Moderate (III)' },
  { value: 'NEGLIGIBLE', label: 'Negligible (IV)' },
];

export const hazardFields: FieldDef[] = [
  { name: 'hazard_description', label: 'Hazard', type: 'textarea', required: true },
  { name: 'category', label: 'Category', type: 'select', required: true, options: HAZARD_CATEGORY_OPTIONS, defaultValue: 'OTHER', span: 2 },
  { name: 'probability', label: 'Probability', type: 'select', required: true, options: PROBABILITY_OPTIONS, defaultValue: 'OCCASIONAL' },
  { name: 'severity', label: 'Severity', type: 'select', required: true, options: SEVERITY_OPTIONS, defaultValue: 'MODERATE' },
  { name: 'existing_controls', label: 'Existing Controls', type: 'textarea' },
  { name: 'additional_controls', label: 'Additional Controls', type: 'textarea' },
  {
    name: 'residual_probability', label: 'Residual Probability', type: 'select', options: PROBABILITY_OPTIONS,
    help: 'Re-assessed after controls. Set together with residual severity.',
  },
  { name: 'residual_severity', label: 'Residual Severity', type: 'select', options: SEVERITY_OPTIONS },
];
