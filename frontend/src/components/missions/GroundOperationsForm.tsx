import { useEffect, useMemo, useState } from 'react';

import { sectionsApi, unitsApi } from '@/api/endpoints';
import { missionOpsApi } from '@/api/missionOps';
import { SearchField, SelectField, TextAreaField, TextField } from '@/components/common/FormFields';
import type { Section, Unit } from '@/types';
import type { AuthorityOption, RoleOption } from '@/types/missionOps';
import { clearError, type FieldErrors } from '@/utils/formErrors';
import { moveItem, removeAt, replaceAt, type GroundForm, type VehicleInput } from '@/utils/missionForm';

import type { KnownPlace } from './LocationPicker';
import PersonnelAssignments from './PersonnelAssignments';
import VehicleTripModal from './VehicleTripModal';

export interface CategoryFormProps<S> {
  form: S;
  onChange: (next: S) => void;
  errors: FieldErrors;
  setErrors: (updater: (e: FieldErrors) => FieldErrors) => void;
  roles: RoleOption[];
  knownPlaces: KnownPlace[];
}

function Section({ n, title, hint, children }: { n: number; title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="ops-card space-y-3 p-5">
      <div>
        <p className="ops-label">{n} · {title}</p>
        {hint && <p className="mt-1 text-xs text-ops-textDim">{hint}</p>}
      </div>
      {children}
    </section>
  );
}

export default function GroundOperationsForm({ form, onChange, errors, setErrors, roles, knownPlaces }: CategoryFormProps<GroundForm>) {
  const [units, setUnits] = useState<Unit[]>([]);
  const [sections, setSections] = useState<Section[]>([]);
  const [authorities, setAuthorities] = useState<AuthorityOption[]>([]);
  const [vehicleModal, setVehicleModal] = useState<{ index: number | null } | null>(null);

  const set = <K extends keyof GroundForm>(key: K, value: GroundForm[K], ...clear: string[]) => {
    onChange({ ...form, [key]: value });
    setErrors((e) => clearError(e, key as string, ...clear, '_general'));
  };

  useEffect(() => { unitsApi.list().then((d) => setUnits(d.results.filter((u) => u.is_active))).catch(() => {}); }, []);

  // O/SPR options follow the chosen UPR; the authority list follows it too (hierarchy + permissions are server-side).
  useEffect(() => {
    if (!form.unit) { setSections([]); setAuthorities([]); return; }
    let live = true;
    sectionsApi.list({ unit: form.unit, is_active: true, page_size: 200 }).then((d) => { if (live) setSections(d.results); }).catch(() => live && setSections([]));
    missionOpsApi.authorities(form.unit).then((a) => { if (live) setAuthorities(a); }).catch(() => live && setAuthorities([]));
    return () => { live = false; };
  }, [form.unit]);

  const onUnit = (unit: string | null) => {
    // never keep a section/authority that belongs to the previous unit
    onChange({ ...form, unit, responsible_section: null, approval_authority: null });
    setErrors((e) => clearError(e, 'unit', 'responsible_section', 'approval_authority'));
  };

  const mrmOptions = useMemo(() => form.personnel.filter((p) => p.mrmReady).map((p) => ({ value: p.personnel, label: p.label })), [form.personnel]);
  const personIds = form.personnel.map((p) => p.personnel);

  // drop a driver / MRM assignee if that person is removed from the crew (keeps the payload consistent)
  useEffect(() => {
    let next = form;
    if (form.mrm_assignee && !personIds.includes(form.mrm_assignee)) next = { ...next, mrm_assignee: null };
    if (form.vehicles.some((v) => v.driver && !personIds.includes(v.driver))) {
      next = { ...next, vehicles: form.vehicles.map((v) => (v.driver && !personIds.includes(v.driver) ? { ...v, driver: null } : v)) };
    }
    if (next !== form) onChange(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [personIds.join('|')]);

  const vehicleSummary = (v: VehicleInput) => (v.is_pov
    ? `${v.pov.plate_number.toUpperCase()} — ${[v.pov.vehicle_type, v.pov.make, v.pov.model].filter(Boolean).join(' · ')}`
    : v.vehicleLabel);

  return (
    <>
      <Section n={1} title="Mission information">
        <div className="grid gap-3 md:grid-cols-2">
          <div id="field-name" className="md:col-span-2">
            <TextField label="Mission / Activity" required value={form.name} error={errors.name} onChange={(v) => set('name', v)} placeholder="Describe the mission, activity or operational task" />
          </div>
          <div className="md:col-span-2">
            <TextAreaField label="Details" value={form.description} onChange={(v) => set('description', v)} rows={2} />
          </div>
          <div id="field-start_date"><TextField label="Estimated start" required type="datetime-local" value={form.start_date} error={errors.start_date} onChange={(v) => set('start_date', v, 'end_date')} /></div>
          <div id="field-end_date"><TextField label="Estimated end" required type="datetime-local" value={form.end_date} error={errors.end_date} onChange={(v) => set('end_date', v)} /></div>
          <div id="field-unit">
            <SearchField label="Unit Primary Responsible (UPR)" required value={form.unit} error={errors.unit} onChange={onUnit} placeholder="Select the responsible unit…"
                         options={units.map((u) => ({ value: u.id, label: u.name, sublabel: u.code }))} />
          </div>
          <div id="field-responsible_section">
            <SelectField label="Office/Section Primary Responsible (O/SPR)" required value={form.responsible_section ?? ''} error={errors.responsible_section}
                         disabled={!form.unit} onChange={(v) => set('responsible_section', v || null)}
                         placeholder={form.unit ? (sections.length ? '— Select an office/section —' : '— This unit has no sections —') : '— Choose a unit first —'}
                         options={sections.map((s) => ({ value: s.id, label: s.code ? `${s.name} (${s.code})` : s.name }))}
                         help="Only the sections of the selected unit are listed." />
          </div>
        </div>
      </Section>

      <Section n={2} title="Personnel involved" hint="Search the Personnel Inventory and give each person a role. Exactly one Team Leader is required.">
        <div id="field-personnel">
          <PersonnelAssignments value={form.personnel} roles={roles} errors={errors} onChange={(personnel) => set('personnel', personnel, 'personnel')} />
        </div>
      </Section>

      <Section n={3} title="Vehicle trips (optional)" hint="Skip this if the mission needs no transport. A mission can have several vehicles, each with several itinerary legs.">
        {form.vehicles.length === 0 && <p className="text-sm text-ops-textDim">No vehicles added.</p>}
        {form.vehicles.map((v, i) => {
          const vErrors = Object.keys(errors).filter((k) => k.startsWith(`vehicles[${i}]`));
          return (
            <div key={v.key} className={`rounded-md border p-3 ${vErrors.length ? 'border-ops-danger' : 'border-ops-border'}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-ops-text">
                    {vehicleSummary(v) || 'Vehicle not selected'}{' '}
                    {v.is_pov && <span className="ml-1 rounded-full bg-ops-warning/10 px-2 py-0.5 text-[10px] font-semibold uppercase text-ops-warning">POV</span>}
                  </p>
                  <p className="text-xs text-ops-textDim">
                    Driver: {form.personnel.find((p) => p.personnel === v.driver)?.label ?? '—'} · {v.itinerary.length} leg(s)
                  </p>
                  {v.itinerary.map((leg, j) => (
                    <p key={j} className="text-xs text-ops-textDim">{j + 1}. {leg.origin.name || '?'} → {leg.stops.map((s) => `${s.name || '?'} → `).join('')}{leg.destination.name || '?'}</p>
                  ))}
                  {vErrors.length > 0 && <p role="alert" className="mt-1 text-xs text-ops-danger">This vehicle has problems — open it to see them.</p>}
                </div>
                <div className="flex gap-2 text-xs">
                  <button type="button" disabled={i === 0} onClick={() => onChange({ ...form, vehicles: moveItem(form.vehicles, i, i - 1) })} className="text-ops-textDim disabled:opacity-30">↑</button>
                  <button type="button" disabled={i === form.vehicles.length - 1} onClick={() => onChange({ ...form, vehicles: moveItem(form.vehicles, i, i + 1) })} className="text-ops-textDim disabled:opacity-30">↓</button>
                  <button type="button" onClick={() => setVehicleModal({ index: i })} className="text-ops-accent hover:underline">Edit</button>
                  <button type="button" onClick={() => onChange({ ...form, vehicles: removeAt(form.vehicles, i) })} className="text-ops-danger hover:underline">Remove</button>
                </div>
              </div>
            </div>
          );
        })}
        <button type="button" onClick={() => setVehicleModal({ index: null })} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-text hover:border-ops-accent">+ Add vehicle trip</button>
      </Section>

      <Section n={4} title="Approval & risk management">
        <div className="grid gap-3 md:grid-cols-2">
          <div id="field-approval_authority">
            <SelectField label="Authority (approves this mission)" required value={form.approval_authority ?? ''} error={errors.approval_authority}
                         disabled={!form.unit} onChange={(v) => set('approval_authority', v || null)}
                         placeholder={form.unit ? (authorities.length ? '— Select the approving authority —' : '— No eligible authority —') : '— Choose a unit first —'}
                         options={authorities.map((a) => ({ value: a.id, label: `${a.name} — ${a.designation}${a.unit ? ` (${a.unit})` : ''}` }))}
                         help="Commanders of the selected unit or its mother units who may approve missions. Required to submit." />
          </div>
          <div id="field-mrm_assignee">
            <SelectField label="MRM assignee (prepares the risk assessment)" required value={form.mrm_assignee ?? ''} error={errors.mrm_assignee}
                         onChange={(v) => set('mrm_assignee', v || null)}
                         placeholder={mrmOptions.length ? '— Select from assigned personnel —' : '— No eligible personnel assigned —'}
                         options={mrmOptions}
                         help={form.personnel.length && mrmOptions.length === 0
                           ? 'None of the assigned personnel has an account that can prepare MRM forms. Add someone who does.'
                           : 'Only assigned personnel with an MRM-capable account are listed. Required to submit.'} />
          </div>
        </div>
        <p className="text-xs text-ops-textDim">Mission approval and MRM preparation are separate: the authority approves the mission; the assignee prepares the MRM, which has its own review.</p>
      </Section>

      {vehicleModal && (
        <VehicleTripModal
          initial={vehicleModal.index === null ? null : form.vehicles[vehicleModal.index]}
          personnel={form.personnel}
          others={form.vehicles.filter((_, i) => i !== vehicleModal.index)}
          knownPlaces={knownPlaces}
          onClose={() => setVehicleModal(null)}
          onSave={(vehicle) => {
            const vehicles = vehicleModal.index === null ? [...form.vehicles, vehicle] : replaceAt(form.vehicles, vehicleModal.index, vehicle);
            onChange({ ...form, vehicles });
            setErrors((e) => Object.fromEntries(Object.entries(e).filter(([k]) => !k.startsWith('vehicles['))));
            setVehicleModal(null);
          }}
        />
      )}
    </>
  );
}
