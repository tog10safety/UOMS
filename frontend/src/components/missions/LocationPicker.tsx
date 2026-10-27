import { useMemo, useState } from 'react';

import { coordsApi } from '@/api/missionOps';
import { SearchField, TextField, inputClass } from '@/components/common/FormFields';
import type { SearchableOption } from '@/components/common/SearchableSelect';
import type { FieldErrors } from '@/utils/formErrors';
import { coordsInRange, hasCoords, type PlaceInput } from '@/utils/missionForm';

import MapPicker from './MapPicker';

export interface KnownPlace { id: string; name: string; kind: string; lat: number; lng: number; mgrs: string }

interface Props {
  label: string;
  /** error-key prefix, e.g. "vehicles[0].itinerary[1].origin" */
  path: string;
  value: PlaceInput;
  onChange: (next: PlaceInput) => void;
  errors: FieldErrors;
  knownPlaces?: KnownPlace[];
}

const round = (n: number) => String(Number(n.toFixed(6)));

/**
 * One place on an itinerary. A location can be set three ways — click the map, type an MGRS grid reference, or type
 * latitude/longitude — and each keeps the others in sync, so a typed MGRS is shown on the map for verification.
 */
export default function LocationPicker({ label, path, value, onChange, errors, knownPlaces = [] }: Props) {
  const [showMap, setShowMap] = useState(false);
  const [mgrsError, setMgrsError] = useState('');
  const [busy, setBusy] = useState(false);

  const options: SearchableOption[] = useMemo(
    () => knownPlaces.map((p) => ({ value: p.id, label: p.name, sublabel: `${p.kind} · ${p.mgrs}` })),
    [knownPlaces],
  );

  const nameErr = errors[`${path}.name`];
  const locErr = errors[`${path}.location`];
  const mgrsErr = mgrsError || errors[`${path}.mgrs`];

  const setCoords = async (lat: number, lng: number) => {
    const mgrs = await coordsApi.toMgrs(lat, lng);
    setMgrsError('');
    onChange({ ...value, lat: round(lat), lng: round(lng), mgrs });
  };

  const locateMgrs = async () => {
    if (!value.mgrs.trim()) return;
    setBusy(true);
    const result = await coordsApi.parseMgrs(value.mgrs);
    setBusy(false);
    if (!result.ok) { setMgrsError(result.message); return; }
    setMgrsError('');
    onChange({ ...value, lat: round(result.lat), lng: round(result.lng), mgrs: result.mgrs });
    setShowMap(true);
  };

  const pickKnown = (id: string | null) => {
    const place = knownPlaces.find((p) => p.id === id);
    if (!place) return;
    setMgrsError('');
    onChange({ name: value.name || place.name, lat: round(place.lat), lng: round(place.lng), mgrs: place.mgrs });
  };

  return (
    <fieldset className="space-y-2 rounded-md border border-ops-border p-3">
      <legend className="px-1 text-xs font-semibold uppercase tracking-wider text-ops-textDim">{label}</legend>

      <TextField label="Place name" required value={value.name} error={nameErr} onChange={(v) => onChange({ ...value, name: v })} placeholder="e.g. Camp Evangelista gate" />

      {options.length > 0 && (
        <SearchField label="Search known locations" value={null} onChange={pickKnown} options={options} placeholder="Checkpoints, landing zones…"
                     help="Fills in the name and position from UOMS map data. Use the map or MGRS below for any other place." />
      )}

      <div>
        <label className="mb-1 block text-xs text-ops-textDim">MGRS grid reference</label>
        <div className="flex gap-2">
          <input
            value={value.mgrs}
            onChange={(e) => { setMgrsError(''); onChange({ ...value, mgrs: e.target.value }); }}
            onBlur={() => { if (value.mgrs.trim() && !hasCoords(value)) void locateMgrs(); }}
            placeholder="51P XQ 81324 37990"
            className={`${inputClass} font-mono ${mgrsErr ? '!border-ops-danger' : ''}`}
            aria-invalid={!!mgrsErr}
          />
          <button type="button" onClick={locateMgrs} disabled={busy || !value.mgrs.trim()}
                  className="whitespace-nowrap rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-text hover:border-ops-accent disabled:opacity-40">
            {busy ? 'Locating…' : 'Show on map'}
          </button>
        </div>
        {mgrsErr && <p role="alert" className="mt-1 text-xs text-ops-danger">{mgrsErr}</p>}
      </div>

      <div className="grid grid-cols-2 gap-2">
        <TextField label="Latitude" type="number" step="any" value={value.lat} onChange={(v) => onChange({ ...value, lat: v })}
                   placeholder="8.4822" />
        <TextField label="Longitude" type="number" step="any" value={value.lng} onChange={(v) => onChange({ ...value, lng: v })}
                   placeholder="124.6472" />
      </div>
      {coordsInRange(value) && !value.mgrs.trim() && (
        <button type="button" onClick={() => setCoords(Number(value.lat), Number(value.lng))} className="text-xs text-ops-accent hover:underline">
          Fill MGRS from these coordinates
        </button>
      )}
      {locErr && <p role="alert" className="text-xs text-ops-danger">{locErr}</p>}

      <button type="button" onClick={() => setShowMap((s) => !s)} className="text-xs text-ops-accent hover:underline">
        {showMap ? 'Hide map' : 'Pick on map'}
      </button>
      {showMap && (
        <div className="space-y-1">
          <MapPicker lat={coordsInRange(value) ? Number(value.lat) : null} lng={coordsInRange(value) ? Number(value.lng) : null} onPick={setCoords} />
          <p className="text-[10px] text-ops-textDim">Click the map to set the position. The marker shows the coordinates currently entered.</p>
        </div>
      )}
    </fieldset>
  );
}
