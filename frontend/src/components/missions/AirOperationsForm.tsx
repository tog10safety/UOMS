import type { CategoryFormProps } from './GroundOperationsForm';

/**
 * EXTENSION POINT — Air Operations (flight missions).
 *
 * The flight-mission field structure has not been specified yet, so this is intentionally a placeholder and the backend
 * refuses to create Air missions. To add it later: (1) fill in `AirOperationsSpec` in apps/missions/ground.py,
 * (2) replace this component and the `air` entry in ./categories.ts with its form state, validator and payload builder.
 * Nothing in the Ground Operations form, the mission detail page or the approval workflow needs to change.
 */
export default function AirOperationsForm(_props: CategoryFormProps<Record<string, never>>) {
  return (
    <section className="ops-card space-y-2 p-6">
      <p className="ops-label">Air Operations</p>
      <p className="text-sm text-ops-text">The flight mission form is not available yet.</p>
      <p className="text-xs text-ops-textDim">
        Its fields are still to be defined. Please create ground missions with <b>Ground Operations</b> for now — flight missions will appear here
        once the requirements are provided.
      </p>
    </section>
  );
}
