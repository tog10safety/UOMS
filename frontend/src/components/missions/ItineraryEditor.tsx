import { TextAreaField, TextField } from '@/components/common/FormFields';
import type { FieldErrors } from '@/utils/formErrors';
import { emptyLeg, emptyStop, moveItem, removeAt, replaceAt, type LegInput } from '@/utils/missionForm';

import LocationPicker, { type KnownPlace } from './LocationPicker';

interface Props {
  legs: LegInput[];
  onChange: (next: LegInput[]) => void;
  /** error-key prefix of the owning vehicle, e.g. "vehicles[0]" */
  path: string;
  errors: FieldErrors;
  knownPlaces: KnownPlace[];
}

const btn = 'rounded border border-ops-border px-2 py-0.5 text-[11px] text-ops-textDim hover:text-ops-text disabled:opacity-30';

/** Ordered itinerary legs (origin → stops → destination) for one vehicle: add, edit, reorder, remove. */
export default function ItineraryEditor({ legs, onChange, path, errors, knownPlaces }: Props) {
  const addLeg = () => {
    const previous = legs[legs.length - 1];
    const leg = emptyLeg();
    if (previous) leg.origin = { ...previous.destination };       // legs usually chain: the next one starts where the last ended
    onChange([...legs, leg]);
  };

  return (
    <div className="space-y-3">
      {legs.length === 0 && <p className="text-xs text-ops-textDim">No itinerary yet. Add at least one leg if this vehicle will travel.</p>}
      {legs.map((leg, i) => {
        const lp = `${path}.itinerary[${i}]`;
        const setLeg = (patch: Partial<LegInput>) => onChange(replaceAt(legs, i, { ...leg, ...patch }));
        return (
          <section key={i} className="space-y-3 rounded-md border border-ops-border bg-ops-panelLight/30 p-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold text-ops-text">Leg {i + 1}</p>
              <div className="flex gap-1">
                <button type="button" className={btn} disabled={i === 0} onClick={() => onChange(moveItem(legs, i, i - 1))}>↑ Up</button>
                <button type="button" className={btn} disabled={i === legs.length - 1} onClick={() => onChange(moveItem(legs, i, i + 1))}>↓ Down</button>
                <button type="button" className={`${btn} !text-ops-danger`} onClick={() => onChange(removeAt(legs, i))}>Remove leg</button>
              </div>
            </div>

            <LocationPicker label="Origin" path={`${lp}.origin`} value={leg.origin} errors={errors} knownPlaces={knownPlaces}
                            onChange={(origin) => setLeg({ origin })} />

            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wider text-ops-textDim">Intermediate stops (in travel order)</p>
              {leg.stops.map((stop, k) => (
                <div key={k} className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-ops-textDim">Stop {k + 1}</span>
                    <div className="flex gap-1">
                      <button type="button" className={btn} disabled={k === 0} onClick={() => setLeg({ stops: moveItem(leg.stops, k, k - 1) })}>↑</button>
                      <button type="button" className={btn} disabled={k === leg.stops.length - 1} onClick={() => setLeg({ stops: moveItem(leg.stops, k, k + 1) })}>↓</button>
                      <button type="button" className={`${btn} !text-ops-danger`} onClick={() => setLeg({ stops: removeAt(leg.stops, k) })}>Remove</button>
                    </div>
                  </div>
                  <LocationPicker label={`Stop ${k + 1}`} path={`${lp}.stops[${k}]`} value={stop} errors={errors} knownPlaces={knownPlaces}
                                  onChange={(next) => setLeg({ stops: replaceAt(leg.stops, k, { ...stop, ...next }) })} />
                </div>
              ))}
              <button type="button" onClick={() => setLeg({ stops: [...leg.stops, emptyStop()] })} className="text-xs text-ops-accent hover:underline">+ Add a stop</button>
            </div>

            <LocationPicker label="Destination" path={`${lp}.destination`} value={leg.destination} errors={errors} knownPlaces={knownPlaces}
                            onChange={(destination) => setLeg({ destination })} />

            <div className="grid gap-3 md:grid-cols-2">
              <TextField label="Planned departure" type="datetime-local" value={leg.planned_departure} error={errors[`${lp}.planned_departure`]}
                         onChange={(v) => setLeg({ planned_departure: v })} />
              <TextField label="Planned arrival" type="datetime-local" value={leg.planned_arrival} error={errors[`${lp}.planned_arrival`]}
                         onChange={(v) => setLeg({ planned_arrival: v })} />
            </div>
            <TextAreaField label="Leg notes" value={leg.notes} onChange={(v) => setLeg({ notes: v })} rows={2} />
          </section>
        );
      })}
      <button type="button" onClick={addLeg} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-text hover:border-ops-accent">+ Add itinerary leg</button>
    </div>
  );
}
