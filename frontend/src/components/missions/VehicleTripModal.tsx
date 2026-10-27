import { useEffect, useMemo, useState } from 'react';

import { vehiclesApi } from '@/api/endpoints';
import { SearchField, SelectField, TextAreaField, TextField } from '@/components/common/FormFields';
import Modal from '@/components/common/Modal';
import type { SearchableOption } from '@/components/common/SearchableSelect';
import type { VehicleListItem } from '@/types';
import { clearError, type FieldErrors } from '@/utils/formErrors';
import { emptyVehicle, validateVehicle, type PersonInput, type VehicleInput } from '@/utils/missionForm';

import ItineraryEditor from './ItineraryEditor';
import type { KnownPlace } from './LocationPicker';

interface Props {
  /** null = adding a new vehicle */
  initial: VehicleInput | null;
  personnel: PersonInput[];
  /** the other vehicles already on the mission (for duplicate checks) */
  others: VehicleInput[];
  knownPlaces: KnownPlace[];
  onSave: (vehicle: VehicleInput) => void;
  onClose: () => void;
}

const vehicleLabel = (v: VehicleListItem) => `${v.plate_number} — ${[v.vehicle_type, v.make, v.model].filter(Boolean).join(' · ') || 'vehicle'}`;

/**
 * Optional "Add Vehicle Trip": pick an official vehicle (or enter a Privately Owned Vehicle) and build its itinerary legs.
 * POVs carry no odometer and never touch the fleet records.
 */
export default function VehicleTripModal({ initial, personnel, others, knownPlaces, onSave, onClose }: Props) {
  const [draft, setDraft] = useState<VehicleInput>(() => initial ?? emptyVehicle());
  const [errors, setErrors] = useState<FieldErrors>({});
  const [query, setQuery] = useState('');
  const [found, setFound] = useState<VehicleListItem[]>([]);

  useEffect(() => {
    if (draft.is_pov) return;
    const timer = setTimeout(() => {
      vehiclesApi.list({ search: query.trim(), page_size: 20 }).then((d) => setFound(d.results.filter((v) => v.is_active))).catch(() => setFound([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [query, draft.is_pov]);

  const options: SearchableOption[] = useMemo(() => {
    const list = found.map((v) => ({ value: v.id, label: vehicleLabel(v), sublabel: `${v.status.replace('_', ' ')} · ${v.odometer_km.toLocaleString()} km` }));
    if (draft.vehicle && !list.some((o) => o.value === draft.vehicle)) list.unshift({ value: draft.vehicle, label: draft.vehicleLabel, sublabel: '' });
    return list;
  }, [found, draft.vehicle, draft.vehicleLabel]);

  const patch = (p: Partial<VehicleInput>, ...clear: string[]) => { setDraft((d) => ({ ...d, ...p })); setErrors((e) => clearError(e, ...clear)); };
  const setPov = (field: keyof VehicleInput['pov'], v: string) => {
    setDraft((d) => ({ ...d, pov: { ...d.pov, [field]: v } }));
    setErrors((e) => clearError(e, `vehicles[0].pov.${field}`));
  };

  const save = () => {
    const personIds = new Set(personnel.map((p) => p.personnel));
    const e = validateVehicle(draft, 0, personIds, {});
    if (!draft.is_pov && draft.vehicle && others.some((o) => !o.is_pov && o.vehicle === draft.vehicle)) e['vehicles[0].vehicle'] = `${draft.vehicleLabel} is already on this mission.`;
    if (draft.is_pov && others.some((o) => o.is_pov && o.pov.plate_number.trim().toUpperCase() === draft.pov.plate_number.trim().toUpperCase() && draft.pov.plate_number.trim())) {
      e['vehicles[0].pov.plate_number'] = `POV ${draft.pov.plate_number.trim().toUpperCase()} is already on this mission.`;
    }
    setErrors(e);
    if (Object.keys(e).length === 0) onSave(draft);
  };

  const err = (k: string) => errors[`vehicles[0].${k}`];

  return (
    <Modal title={initial ? 'Edit vehicle trip' : 'Add vehicle trip'} width="xl" onClose={onClose}>
      <div className="space-y-4">
        <div role="radiogroup" aria-label="Vehicle source" className="flex flex-wrap gap-4 text-sm text-ops-text">
          <label className="flex cursor-pointer items-center gap-2">
            <input type="radio" checked={!draft.is_pov} onChange={() => patch({ is_pov: false }, 'vehicles[0].vehicle')} /> Official vehicle (Vehicle Inventory)
          </label>
          <label className="flex cursor-pointer items-center gap-2">
            <input type="radio" checked={draft.is_pov} onChange={() => patch({ is_pov: true, vehicle: null, vehicleLabel: '' })} /> Privately Owned Vehicle (POV)
          </label>
        </div>

        {!draft.is_pov ? (
          <div className="space-y-2">
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter by plate, type or make…"
                   className="w-full max-w-sm rounded-md border border-ops-border bg-ops-panelLight px-3 py-1.5 text-xs text-ops-text outline-none focus:border-ops-accent" />
            <SearchField label="Vehicle" required value={draft.vehicle} error={err('vehicle')} options={options} placeholder="Select a vehicle…"
                         onChange={(id) => patch({ vehicle: id, vehicleLabel: options.find((o) => o.value === id)?.label ?? '' }, 'vehicles[0].vehicle')} />
          </div>
        ) : (
          <div className="space-y-3 rounded-md border border-ops-warning/40 bg-ops-warning/5 p-3">
            <p className="text-xs text-ops-warning">Privately owned vehicle — recorded for this mission only. It is not part of the fleet: no odometer is tracked and no fleet record is created or changed.</p>
            <div className="grid gap-3 md:grid-cols-2">
              <TextField label="Plate number" required value={draft.pov.plate_number} error={err('pov.plate_number')} onChange={(v) => setPov('plate_number', v)} />
              <TextField label="Vehicle type" required value={draft.pov.vehicle_type} error={err('pov.vehicle_type')} onChange={(v) => setPov('vehicle_type', v)} placeholder="Sedan, pickup, motorcycle…" />
              <TextField label="Make" value={draft.pov.make} onChange={(v) => setPov('make', v)} />
              <TextField label="Model" value={draft.pov.model} onChange={(v) => setPov('model', v)} />
              <TextField label="Colour" value={draft.pov.color} onChange={(v) => setPov('color', v)} />
              <TextField label="Owner" value={draft.pov.owner_name} onChange={(v) => setPov('owner_name', v)} />
            </div>
            <TextAreaField label="Other identifying details" value={draft.pov.description} onChange={(v) => setPov('description', v)} rows={2} />
          </div>
        )}

        <div className="grid gap-3 md:grid-cols-2">
          <SelectField label="Driver" value={draft.driver ?? ''} error={err('driver')} placeholder="— Not assigned —" allowEmpty
                       onChange={(v) => patch({ driver: v || null }, 'vehicles[0].driver')}
                       options={personnel.map((p) => ({ value: p.personnel, label: p.label }))}
                       help={personnel.length ? 'Choose from the personnel assigned to this mission.' : 'Assign personnel to the mission first.'} />
          <TextField label="Notes" value={draft.notes} onChange={(v) => patch({ notes: v })} />
        </div>

        <div className="space-y-2">
          <p className="ops-label">Itinerary</p>
          <ItineraryEditor legs={draft.itinerary} path="vehicles[0]" errors={errors} knownPlaces={knownPlaces} onChange={(itinerary) => patch({ itinerary })} />
        </div>

        {Object.keys(errors).length > 0 && <p className="text-xs text-ops-danger">Some fields need attention — they are marked above.</p>}
        <div className="flex justify-end gap-2 border-t border-ops-border pt-3">
          <button type="button" onClick={onClose} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-textDim">Cancel</button>
          <button type="button" onClick={save} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg">{initial ? 'Update vehicle' : 'Add vehicle to mission'}</button>
        </div>
      </div>
    </Modal>
  );
}
