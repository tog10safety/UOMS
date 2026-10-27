import { FormEvent, useEffect, useState } from 'react';

import { aircraftApi, personnelApi } from '@/api/endpoints';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import { SearchField, SelectField, TextField } from '@/components/common/FormFields';
import Modal from '@/components/common/Modal';
import { useAuth } from '@/contexts/AuthContext';
import { useToast } from '@/contexts/ToastContext';
import type { FlightCrewAssignment, FlightDetail, FlightListItem, PersonnelListItem } from '@/types';
import { extractApiError, formatDateTime, fromDatetimeLocal } from '@/utils/errors';

const CREW_ROLES: { value: FlightCrewAssignment['crew_role']; label: string }[] = [
  { value: 'PIC', label: 'Pilot in Command' },
  { value: 'CO_PILOT', label: 'Co-Pilot' },
  { value: 'FLIGHT_ENGINEER', label: 'Flight Engineer' },
  { value: 'LOADMASTER', label: 'Loadmaster' },
  { value: 'CREW_CHIEF', label: 'Crew Chief' },
  { value: 'OTHER', label: 'Other' },
];

const emptyWaypoint = { sequence: '', name: '', lat: '', lng: '', eta: '', notes: '' };

interface Props {
  flight: FlightListItem;
  onClose: () => void;
}

export default function FlightDetailModal({ flight, onClose }: Props) {
  const { can } = useAuth();
  const { showSuccess, showError } = useToast();

  const [detail, setDetail] = useState<FlightDetail | null>(null);
  const [personnel, setPersonnel] = useState<PersonnelListItem[]>([]);
  const [error, setError] = useState('');

  const [crewForm, setCrewForm] = useState({ personnel: null as string | null, crew_role: 'PIC' as FlightCrewAssignment['crew_role'] });
  const [waypointForm, setWaypointForm] = useState(emptyWaypoint);
  const [isSaving, setIsSaving] = useState(false);
  const [pendingRemoval, setPendingRemoval] = useState<FlightCrewAssignment | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  // The nested crew/waypoint endpoints are gated by the plain HTTP-method permission (CREATE for POST).
  const canAdd = can('AIRCRAFT', 'CREATE');
  const canEditCrew = can('AIRCRAFT', 'EDIT');
  const canRemoveCrew = can('AIRCRAFT', 'DELETE');

  const load = () =>
    aircraftApi
      .getFlight(flight.id)
      .then(setDetail)
      .catch((err) => setError(extractApiError(err, 'Unable to load flight details.')));

  useEffect(() => {
    load();
    personnelApi.list({ page_size: 200 }).then((d) => setPersonnel(d.results)).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flight.id]);

  const nextSequence = (detail?.waypoints.reduce((max, w) => Math.max(max, w.sequence), 0) ?? 0) + 1;

  const addCrew = async (e: FormEvent) => {
    e.preventDefault();
    if (!crewForm.personnel) return;
    setIsSaving(true);
    setError('');
    try {
      await aircraftApi.addFlightCrew(flight.id, { personnel: crewForm.personnel, crew_role: crewForm.crew_role });
      showSuccess('Crew member assigned.');
      setCrewForm({ personnel: null, crew_role: 'PIC' });
      await load();
    } catch (err) {
      setError(extractApiError(err, 'Unable to assign crew member.'));
    } finally {
      setIsSaving(false);
    }
  };

  const changeRole = async (assignment: FlightCrewAssignment, role: FlightCrewAssignment['crew_role']) => {
    try {
      await aircraftApi.updateCrewAssignment(assignment.id, { crew_role: role });
      showSuccess(`${assignment.personnel_name} reassigned.`);
      await load();
    } catch (err) {
      showError(extractApiError(err, 'Unable to change crew role.'));
    }
  };

  const removeCrew = async () => {
    if (!pendingRemoval) return;
    setIsBusy(true);
    try {
      await aircraftApi.removeCrewAssignment(pendingRemoval.id);
      showSuccess(`${pendingRemoval.personnel_name} removed from the crew.`);
      setPendingRemoval(null);
      await load();
    } catch (err) {
      showError(extractApiError(err, 'Unable to remove crew member.'));
    } finally {
      setIsBusy(false);
    }
  };

  const addWaypoint = async (e: FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setError('');
    try {
      const hasCoords = waypointForm.lat !== '' && waypointForm.lng !== '';
      await aircraftApi.addFlightWaypoint(flight.id, {
        sequence: Number(waypointForm.sequence || nextSequence),
        name: waypointForm.name,
        notes: waypointForm.notes,
        eta: fromDatetimeLocal(waypointForm.eta),
        ...(hasCoords ? { location_input: { lat: Number(waypointForm.lat), lng: Number(waypointForm.lng) } } : {}),
      });
      showSuccess('Waypoint added.');
      setWaypointForm(emptyWaypoint);
      await load();
    } catch (err) {
      setError(extractApiError(err, 'Unable to add waypoint.'));
    } finally {
      setIsSaving(false);
    }
  };

  const assignedIds = new Set(detail?.crew_assignments.map((c) => c.personnel));
  const personnelOptions = personnel
    .filter((p) => !assignedIds.has(p.id))
    .map((p) => ({ value: p.id, label: p.full_name, sublabel: p.service_number }));

  return (
    <Modal title={`Flight ${flight.flight_number} — ${flight.origin} → ${flight.destination}`} width="xl" onClose={onClose}>
      <div className="grid grid-cols-2 gap-4 text-xs md:grid-cols-4">
        <div><p className="ops-label">Aircraft</p><p className="text-ops-text">{flight.aircraft_tail_number}</p></div>
        <div><p className="ops-label">Status</p><p className="text-ops-text">{flight.status.replace('_', ' ')}</p></div>
        <div><p className="ops-label">Scheduled Dep.</p><p className="text-ops-text">{formatDateTime(flight.scheduled_departure)}</p></div>
        <div><p className="ops-label">Scheduled Arr.</p><p className="text-ops-text">{formatDateTime(flight.scheduled_arrival)}</p></div>
        {detail && (
          <>
            <div><p className="ops-label">CAAP Flight Plan</p><p className="text-ops-text">{detail.caap_flight_plan_number || '—'}</p></div>
            <div><p className="ops-label">CAAP Registration</p><p className="text-ops-text">{detail.caap_aircraft_registration || '—'}</p></div>
            <div className="col-span-2"><p className="ops-label">CAAP Remarks</p><p className="text-ops-text">{detail.caap_remarks || '—'}</p></div>
          </>
        )}
      </div>

      {error && <p className="text-xs text-ops-danger">{error}</p>}

      {/* Crew */}
      <div className="space-y-2 border-t border-ops-border pt-3">
        <p className="ops-label">Flight Crew</p>
        <div className="overflow-hidden rounded-md border border-ops-border">
          <table className="w-full text-left text-sm">
            <thead className="bg-ops-panelLight text-xs uppercase tracking-wider text-ops-textDim">
              <tr><th className="px-3 py-2">Name</th><th className="px-3 py-2">Role</th><th className="px-3 py-2" /></tr>
            </thead>
            <tbody>
              {detail && detail.crew_assignments.length === 0 && (
                <tr><td colSpan={3} className="px-3 py-4 text-center text-xs text-ops-textDim">No crew assigned yet.</td></tr>
              )}
              {detail?.crew_assignments.map((c) => (
                <tr key={c.id} className="border-t border-ops-border">
                  <td className="px-3 py-2">{c.personnel_name}</td>
                  <td className="px-3 py-2">
                    {canEditCrew ? (
                      <select
                        value={c.crew_role}
                        onChange={(e) => changeRole(c, e.target.value as FlightCrewAssignment['crew_role'])}
                        className="rounded-md border border-ops-border bg-ops-panelLight px-2 py-1 text-xs text-ops-text"
                      >
                        {CREW_ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                      </select>
                    ) : (
                      CREW_ROLES.find((r) => r.value === c.crew_role)?.label
                    )}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {canRemoveCrew && (
                      <button onClick={() => setPendingRemoval(c)} className="text-xs font-medium text-ops-danger hover:underline">Remove</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {canAdd && (
          <form onSubmit={addCrew} className="grid grid-cols-1 items-end gap-3 md:grid-cols-[1fr_1fr_auto]">
            <SearchField label="Add crew member" value={crewForm.personnel} onChange={(v) => setCrewForm({ ...crewForm, personnel: v })} options={personnelOptions} placeholder="Search personnel…" />
            <SelectField label="Role" required value={crewForm.crew_role} onChange={(v) => setCrewForm({ ...crewForm, crew_role: v as FlightCrewAssignment['crew_role'] })} options={CREW_ROLES} />
            <button type="submit" disabled={isSaving || !crewForm.personnel} className="rounded-md bg-ops-accent px-3 py-2 text-xs font-semibold text-ops-bg disabled:opacity-50">
              Assign
            </button>
          </form>
        )}
      </div>

      {/* Waypoints */}
      <div className="space-y-2 border-t border-ops-border pt-3">
        <p className="ops-label">Itinerary / Waypoints</p>
        <div className="overflow-hidden rounded-md border border-ops-border">
          <table className="w-full text-left text-sm">
            <thead className="bg-ops-panelLight text-xs uppercase tracking-wider text-ops-textDim">
              <tr>
                <th className="px-3 py-2">#</th><th className="px-3 py-2">Waypoint</th><th className="px-3 py-2">Position</th>
                <th className="px-3 py-2">ETA</th><th className="px-3 py-2">Notes</th>
              </tr>
            </thead>
            <tbody>
              {detail && detail.waypoints.length === 0 && (
                <tr><td colSpan={5} className="px-3 py-4 text-center text-xs text-ops-textDim">No waypoints recorded.</td></tr>
              )}
              {detail?.waypoints.map((w) => (
                <tr key={w.id} className="border-t border-ops-border">
                  <td className="px-3 py-2 font-mono text-xs">{w.sequence}</td>
                  <td className="px-3 py-2">{w.name}</td>
                  <td className="px-3 py-2 font-mono text-xs text-ops-textDim">{w.location ? `${w.location.lat.toFixed(4)}, ${w.location.lng.toFixed(4)}` : '—'}</td>
                  <td className="px-3 py-2 text-xs text-ops-textDim">{formatDateTime(w.eta)}</td>
                  <td className="px-3 py-2 text-xs text-ops-textDim">{w.notes || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {canAdd && (
          <form onSubmit={addWaypoint} className="space-y-3">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <TextField label="Sequence" type="number" value={waypointForm.sequence} placeholder={String(nextSequence)} onChange={(v) => setWaypointForm({ ...waypointForm, sequence: v })} />
              <div className="col-span-2 md:col-span-3">
                <TextField label="Waypoint name" required value={waypointForm.name} onChange={(v) => setWaypointForm({ ...waypointForm, name: v })} />
              </div>
              <TextField label="Latitude" type="number" step="any" value={waypointForm.lat} onChange={(v) => setWaypointForm({ ...waypointForm, lat: v })} />
              <TextField label="Longitude" type="number" step="any" value={waypointForm.lng} onChange={(v) => setWaypointForm({ ...waypointForm, lng: v })} />
              <TextField label="ETA" type="datetime-local" value={waypointForm.eta} onChange={(v) => setWaypointForm({ ...waypointForm, eta: v })} />
              <TextField label="Notes" value={waypointForm.notes} onChange={(v) => setWaypointForm({ ...waypointForm, notes: v })} />
            </div>
            <div className="flex justify-end">
              <button type="submit" disabled={isSaving} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg disabled:opacity-50">
                Add Waypoint
              </button>
            </div>
          </form>
        )}
        <p className="text-[10px] text-ops-textDim">Waypoints can be added but not edited or removed — the API only supports list and add.</p>
      </div>

      <div className="flex justify-end pt-2">
        <button onClick={onClose} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-textDim">Close</button>
      </div>

      {pendingRemoval && (
        <ConfirmDialog
          title="Remove Crew Member"
          message={`Remove ${pendingRemoval.personnel_name} from flight ${flight.flight_number}?`}
          confirmLabel="Remove"
          danger
          isBusy={isBusy}
          onConfirm={removeCrew}
          onCancel={() => setPendingRemoval(null)}
        />
      )}
    </Modal>
  );
}
