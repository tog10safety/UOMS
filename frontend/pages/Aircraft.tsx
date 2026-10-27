import { FormEvent, useEffect, useState } from 'react';

import { aircraftApi, missionsApi, unitsApi } from '@/api/endpoints';
import FlightDetailModal from '@/components/aircraft/FlightDetailModal';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import SearchableSelect from '@/components/common/SearchableSelect';
import { useAuth } from '@/contexts/AuthContext';
import { useToast } from '@/contexts/ToastContext';
import type {
  AircraftFlyingStatus,
  AircraftItem,
  FlightDetail,
  FlightListItem,
  FlightStatus,
  MissionListItem,
  Unit,
} from '@/types';

const AIRCRAFT_STATUS_BADGE: Record<AircraftFlyingStatus, string> = {
  GROUNDED: 'bg-ops-textDim/10 text-ops-textDim',
  SCHEDULED: 'bg-ops-warning/10 text-ops-warning',
  IN_FLIGHT: 'bg-ops-accent/10 text-ops-accent',
  MAINTENANCE: 'bg-ops-danger/10 text-ops-danger',
};

const FLIGHT_STATUS_BADGE: Record<FlightStatus, string> = {
  SCHEDULED: 'bg-ops-warning/10 text-ops-warning',
  DEPARTED: 'bg-ops-accent/10 text-ops-accent',
  EN_ROUTE: 'bg-ops-accent/10 text-ops-accent',
  ARRIVED: 'bg-ops-success/10 text-ops-success',
  DELAYED: 'bg-ops-warning/10 text-ops-warning',
  CANCELLED: 'bg-ops-danger/10 text-ops-danger',
};

function formatTime(iso: string | null) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// datetime-local inputs need "YYYY-MM-DDTHH:mm" with no timezone suffix.
function toDatetimeLocal(iso: string) {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const emptyAircraftForm = {
  tail_number: '', aircraft_type: '', manufacturer: '', model: '', capacity: '', base_unit: null as string | null,
  flying_status: '' as AircraftFlyingStatus | '',
};
const emptyFlightForm = {
  flight_number: '', aircraft: '', mission: null as string | null, unit: null as string | null,
  origin: '', destination: '', scheduled_departure: '', scheduled_arrival: '',
  caap_flight_plan_number: '', caap_aircraft_registration: '', caap_remarks: '',
};

export default function Aircraft() {
  const { can } = useAuth();
  const { showSuccess, showError } = useToast();

  const [aircraft, setAircraft] = useState<AircraftItem[]>([]);
  const [flights, setFlights] = useState<FlightListItem[]>([]);
  const [missions, setMissions] = useState<MissionListItem[]>([]);
  const [units, setUnits] = useState<Unit[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionInFlight, setActionInFlight] = useState<string | null>(null);

  const [showAircraftForm, setShowAircraftForm] = useState(false);
  const [editingAircraftId, setEditingAircraftId] = useState<string | null>(null);
  const [aircraftForm, setAircraftForm] = useState(emptyAircraftForm);
  const [aircraftFormError, setAircraftFormError] = useState('');
  const [isSavingAircraft, setIsSavingAircraft] = useState(false);

  const [showFlightForm, setShowFlightForm] = useState(false);
  const [editingFlightId, setEditingFlightId] = useState<string | null>(null);
  const [flightForm, setFlightForm] = useState(emptyFlightForm);
  const [flightFormError, setFlightFormError] = useState('');
  const [isSavingFlight, setIsSavingFlight] = useState(false);

  const [pendingFlightAction, setPendingFlightAction] = useState<
    { type: 'depart' | 'arrive' | 'cancel'; flight: FlightListItem } | null
  >(null);
  const [pendingAircraftArchive, setPendingAircraftArchive] = useState<AircraftItem | null>(null);
  const [detailFlight, setDetailFlight] = useState<FlightListItem | null>(null);
  const [isActionBusy, setIsActionBusy] = useState(false);

  const canCreateAircraft = can('AIRCRAFT', 'CREATE');
  const canEditAircraft = can('AIRCRAFT', 'EDIT');
  const canDeleteAircraft = can('AIRCRAFT', 'DELETE');
  const canCreateFlight = can('AIRCRAFT', 'CREATE');
  const canEditFlight = can('AIRCRAFT', 'EDIT');
  const canDispatchFlight = can('AIRCRAFT', 'DISPATCH');
  const canReturnFlight = can('AIRCRAFT', 'RETURN');
  const canDeleteFlight = can('AIRCRAFT', 'DELETE');

  const loadAircraft = () => aircraftApi.list().then((d) => setAircraft(d.results));
  const loadFlights = () => aircraftApi.flights({ ordering: 'scheduled_departure' }).then((d) => setFlights(d.results));

  useEffect(() => {
    let isMounted = true;
    Promise.all([loadAircraft(), loadFlights()])
      .catch(() => {
        if (isMounted) setError('Unable to load aircraft/flight data.');
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    missionsApi.list({ page_size: 200 }).then((d) => setMissions(d.results)).catch(() => {});
    unitsApi.list().then((d) => setUnits(d.results)).catch(() => {});
  }, []);

  // ---- Aircraft registry form ----
  const openCreateAircraft = () => {
    setEditingAircraftId(null);
    setAircraftForm(emptyAircraftForm);
    setAircraftFormError('');
    setShowAircraftForm(true);
  };

  const openEditAircraft = (a: AircraftItem) => {
    setEditingAircraftId(a.id);
    setAircraftForm({
      tail_number: a.tail_number, aircraft_type: a.aircraft_type, manufacturer: a.manufacturer,
      model: a.model, capacity: a.capacity?.toString() ?? '', base_unit: a.base_unit,
      flying_status: a.flying_status,
    });
    setAircraftFormError('');
    setShowAircraftForm(true);
  };

  const handleAircraftSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setIsSavingAircraft(true);
    setAircraftFormError('');
    const payload = {
      tail_number: aircraftForm.tail_number, aircraft_type: aircraftForm.aircraft_type,
      manufacturer: aircraftForm.manufacturer, model: aircraftForm.model,
      capacity: aircraftForm.capacity ? Number(aircraftForm.capacity) : null, base_unit: aircraftForm.base_unit,
      ...(editingAircraftId && aircraftForm.flying_status ? { flying_status: aircraftForm.flying_status } : {}),
    };
    try {
      if (editingAircraftId) {
        await aircraftApi.updateAircraft(editingAircraftId, payload);
        showSuccess(`Aircraft ${aircraftForm.tail_number} updated successfully.`);
      } else {
        await aircraftApi.createAircraft(payload);
        showSuccess(`Aircraft ${aircraftForm.tail_number} registered successfully.`);
      }
      setShowAircraftForm(false);
      await loadAircraft();
    } catch (err: any) {
      const data = err?.response?.data;
      setAircraftFormError(data ? Object.values(data).flat().join(' ') : 'Unable to save record. Please check the required fields.');
    } finally {
      setIsSavingAircraft(false);
    }
  };

  // ---- Flight schedule form ----
  const openCreateFlight = () => {
    setEditingFlightId(null);
    setFlightForm(emptyFlightForm);
    setFlightFormError('');
    setShowFlightForm(true);
  };

  const openEditFlight = async (flight: FlightListItem) => {
    try {
      const detail: FlightDetail = await aircraftApi.getFlight(flight.id);
      setEditingFlightId(flight.id);
      setFlightForm({
        flight_number: detail.flight_number, aircraft: detail.aircraft, mission: detail.mission, unit: detail.unit,
        origin: detail.origin, destination: detail.destination,
        scheduled_departure: toDatetimeLocal(detail.scheduled_departure), scheduled_arrival: toDatetimeLocal(detail.scheduled_arrival),
        caap_flight_plan_number: detail.caap_flight_plan_number, caap_aircraft_registration: detail.caap_aircraft_registration,
        caap_remarks: detail.caap_remarks,
      });
      setFlightFormError('');
      setShowFlightForm(true);
    } catch {
      showError('Unable to load flight details.');
    }
  };

  const handleFlightSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setIsSavingFlight(true);
    setFlightFormError('');
    const payload = {
      ...flightForm,
      scheduled_departure: flightForm.scheduled_departure ? new Date(flightForm.scheduled_departure).toISOString() : undefined,
      scheduled_arrival: flightForm.scheduled_arrival ? new Date(flightForm.scheduled_arrival).toISOString() : undefined,
    };
    try {
      if (editingFlightId) {
        await aircraftApi.updateFlight(editingFlightId, payload);
        showSuccess(`Flight ${flightForm.flight_number} updated successfully.`);
      } else {
        await aircraftApi.createFlight(payload);
        showSuccess(`Flight ${flightForm.flight_number} scheduled successfully.`);
      }
      setShowFlightForm(false);
      await loadFlights();
    } catch (err: any) {
      const data = err?.response?.data;
      setFlightFormError(data ? Object.values(data).flat().join(' ') : 'Unable to save record. Please check the required fields.');
    } finally {
      setIsSavingFlight(false);
    }
  };

  // ---- Workflow actions ----
  const runPendingFlightAction = async () => {
    if (!pendingFlightAction) return;
    setIsActionBusy(true);
    try {
      if (pendingFlightAction.type === 'depart') {
        await aircraftApi.markDeparted(pendingFlightAction.flight.id);
        showSuccess(`Flight ${pendingFlightAction.flight.flight_number} marked as departed.`);
      } else if (pendingFlightAction.type === 'arrive') {
        await aircraftApi.markArrived(pendingFlightAction.flight.id);
        showSuccess(`Flight ${pendingFlightAction.flight.flight_number} marked as arrived.`);
      } else {
        await aircraftApi.cancelFlight(pendingFlightAction.flight.id);
        showSuccess(`Flight ${pendingFlightAction.flight.flight_number} cancelled.`);
      }
      setPendingFlightAction(null);
      await loadFlights();
    } catch (err: any) {
      showError(err?.response?.data?.detail ?? 'You do not have permission to perform this action.');
    } finally {
      setIsActionBusy(false);
    }
  };

  const runAircraftArchive = async () => {
    if (!pendingAircraftArchive) return;
    setIsActionBusy(true);
    try {
      await aircraftApi.archiveAircraft(pendingAircraftArchive.id);
      showSuccess(`Aircraft ${pendingAircraftArchive.tail_number} archived.`);
      setPendingAircraftArchive(null);
      await loadAircraft();
    } catch (err: any) {
      showError(err?.response?.data?.detail ?? 'You do not have permission to perform this action.');
    } finally {
      setIsActionBusy(false);
    }
  };

  const unitOptions = units.map((u) => ({ value: u.id, label: `${u.code} — ${u.name}` }));
  const aircraftOptions = aircraft.map((a) => ({ value: a.id, label: a.tail_number, sublabel: a.aircraft_type }));
  const missionOptions = missions.map((m) => ({ value: m.id, label: m.name }));

  return (
    <div className="space-y-6">
      {error && <p className="text-sm text-ops-danger">{error}</p>}

      <div>
        <div className="mb-2 flex items-center justify-between">
          <p className="ops-label">Aircraft Registry</p>
          {canCreateAircraft && (
            <button onClick={openCreateAircraft} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg">
              + Add Aircraft
            </button>
          )}
        </div>
        <div className="ops-card overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="bg-ops-panelLight text-xs uppercase tracking-wider text-ops-textDim">
              <tr>
                <th className="px-4 py-3">Tail #</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Base Unit</th>
                <th className="px-4 py-3">Flying Status</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {!isLoading && aircraft.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-ops-textDim">No aircraft registered.</td>
                </tr>
              )}
              {aircraft.map((a) => (
                <tr key={a.id} className="border-t border-ops-border hover:bg-ops-panelLight/50">
                  <td className="px-4 py-3 font-mono text-xs">{a.tail_number}</td>
                  <td className="px-4 py-3">{a.aircraft_type || '—'}</td>
                  <td className="px-4 py-3">{a.base_unit_name ?? '—'}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${AIRCRAFT_STATUS_BADGE[a.flying_status]}`}>
                      {a.flying_status.replace('_', ' ')}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-2">
                      {canEditAircraft && (
                        <button onClick={() => openEditAircraft(a)} className="text-xs font-medium text-ops-textDim hover:text-ops-text">
                          Edit
                        </button>
                      )}
                      {canDeleteAircraft && (
                        <button onClick={() => setPendingAircraftArchive(a)} className="text-xs font-medium text-ops-danger hover:underline">
                          Archive
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <p className="ops-label">Flight Schedule &amp; Monitoring</p>
          {canCreateFlight && (
            <button onClick={openCreateFlight} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg">
              + Schedule Flight
            </button>
          )}
        </div>
        <div className="ops-card overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="bg-ops-panelLight text-xs uppercase tracking-wider text-ops-textDim">
              <tr>
                <th className="px-4 py-3">Flight #</th>
                <th className="px-4 py-3">Aircraft</th>
                <th className="px-4 py-3">Route</th>
                <th className="px-4 py-3">Scheduled Dep / Arr</th>
                <th className="px-4 py-3">Actual Dep / Arr</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {!isLoading && flights.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-6 text-center text-ops-textDim">No flights scheduled.</td>
                </tr>
              )}
              {flights.map((f) => (
                <tr key={f.id} className="border-t border-ops-border hover:bg-ops-panelLight/50">
                  <td className="px-4 py-3 font-mono text-xs">{f.flight_number}</td>
                  <td className="px-4 py-3">{f.aircraft_tail_number}</td>
                  <td className="px-4 py-3">{f.origin} → {f.destination}</td>
                  <td className="px-4 py-3 text-xs text-ops-textDim">
                    {formatTime(f.scheduled_departure)} / {formatTime(f.scheduled_arrival)}
                  </td>
                  <td className="px-4 py-3 text-xs text-ops-textDim">
                    {formatTime(f.actual_departure)} / {formatTime(f.actual_arrival)}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${FLIGHT_STATUS_BADGE[f.status]}`}>
                      {f.status.replace('_', ' ')}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-2 whitespace-nowrap">
                      <button onClick={() => setDetailFlight(f)} className="text-xs font-medium text-ops-textDim hover:text-ops-accent">
                        Crew &amp; Route
                      </button>
                      {canEditFlight && f.status === 'SCHEDULED' && (
                        <button onClick={() => openEditFlight(f)} className="text-xs font-medium text-ops-textDim hover:text-ops-text">
                          Edit
                        </button>
                      )}
                      {canDispatchFlight && f.status === 'SCHEDULED' && (
                        <button
                          disabled={actionInFlight === f.id}
                          onClick={() => setPendingFlightAction({ type: 'depart', flight: f })}
                          className="text-xs font-medium text-ops-accent hover:underline disabled:opacity-50"
                        >
                          Mark Departed
                        </button>
                      )}
                      {canReturnFlight && (f.status === 'DEPARTED' || f.status === 'EN_ROUTE') && (
                        <button
                          disabled={actionInFlight === f.id}
                          onClick={() => setPendingFlightAction({ type: 'arrive', flight: f })}
                          className="text-xs font-medium text-ops-success hover:underline disabled:opacity-50"
                        >
                          Mark Arrived
                        </button>
                      )}
                      {canDeleteFlight && f.status === 'SCHEDULED' && (
                        <button
                          onClick={() => setPendingFlightAction({ type: 'cancel', flight: f })}
                          className="text-xs font-medium text-ops-danger hover:underline"
                        >
                          Cancel
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {showAircraftForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <form onSubmit={handleAircraftSubmit} className="ops-card w-full max-w-lg space-y-3 p-6">
            <p className="ops-label">{editingAircraftId ? 'Edit Aircraft' : 'Add Aircraft'}</p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Tail Number *</label>
                <input
                  required
                  value={aircraftForm.tail_number}
                  onChange={(e) => setAircraftForm({ ...aircraftForm, tail_number: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Aircraft Type</label>
                <input
                  value={aircraftForm.aircraft_type}
                  onChange={(e) => setAircraftForm({ ...aircraftForm, aircraft_type: e.target.value })}
                  placeholder="e.g. Helicopter, Fixed Wing"
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Manufacturer</label>
                <input
                  value={aircraftForm.manufacturer}
                  onChange={(e) => setAircraftForm({ ...aircraftForm, manufacturer: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Model</label>
                <input
                  value={aircraftForm.model}
                  onChange={(e) => setAircraftForm({ ...aircraftForm, model: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Capacity</label>
                <input
                  type="number"
                  value={aircraftForm.capacity}
                  onChange={(e) => setAircraftForm({ ...aircraftForm, capacity: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Base Unit</label>
                <SearchableSelect
                  options={unitOptions}
                  value={aircraftForm.base_unit}
                  onChange={(v) => setAircraftForm({ ...aircraftForm, base_unit: v })}
                  placeholder="Search units…"
                />
              </div>
              {editingAircraftId && (
                <div>
                  <label className="mb-1 block text-xs text-ops-textDim">Flying Status</label>
                  <select
                    value={aircraftForm.flying_status}
                    onChange={(e) => setAircraftForm({ ...aircraftForm, flying_status: e.target.value as AircraftFlyingStatus })}
                    className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text"
                  >
                    {(['GROUNDED', 'SCHEDULED', 'IN_FLIGHT', 'MAINTENANCE'] as AircraftFlyingStatus[]).map((st) => (
                      <option key={st} value={st}>{st.replace('_', ' ')}</option>
                    ))}
                  </select>
                </div>
              )}
            </div>
            {aircraftFormError && <p className="text-xs text-ops-danger">{aircraftFormError}</p>}
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={() => setShowAircraftForm(false)} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-textDim">
                Cancel
              </button>
              <button type="submit" disabled={isSavingAircraft} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg disabled:opacity-50">
                {isSavingAircraft ? 'Saving…' : 'Save'}
              </button>
            </div>
          </form>
        </div>
      )}

      {showFlightForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <form onSubmit={handleFlightSubmit} className="ops-card w-full max-w-lg space-y-3 p-6 max-h-[90vh] overflow-y-auto">
            <p className="ops-label">{editingFlightId ? 'Edit Flight' : 'Schedule Flight'}</p>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Flight Number *</label>
                <input
                  required
                  value={flightForm.flight_number}
                  onChange={(e) => setFlightForm({ ...flightForm, flight_number: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Aircraft *</label>
                <SearchableSelect
                  options={aircraftOptions}
                  value={flightForm.aircraft || null}
                  onChange={(v) => setFlightForm({ ...flightForm, aircraft: v ?? '' })}
                  placeholder="Search aircraft…"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Origin *</label>
                <input
                  required
                  value={flightForm.origin}
                  onChange={(e) => setFlightForm({ ...flightForm, origin: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Destination *</label>
                <input
                  required
                  value={flightForm.destination}
                  onChange={(e) => setFlightForm({ ...flightForm, destination: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Scheduled Departure *</label>
                <input
                  required
                  type="datetime-local"
                  value={flightForm.scheduled_departure}
                  onChange={(e) => setFlightForm({ ...flightForm, scheduled_departure: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Scheduled Arrival *</label>
                <input
                  required
                  type="datetime-local"
                  value={flightForm.scheduled_arrival}
                  onChange={(e) => setFlightForm({ ...flightForm, scheduled_arrival: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
                />
              </div>
            </div>

            <div>
              <label className="mb-1 block text-xs text-ops-textDim">Mission</label>
              <SearchableSelect
                options={missionOptions}
                value={flightForm.mission}
                onChange={(v) => setFlightForm({ ...flightForm, mission: v })}
                placeholder="Search missions…"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs text-ops-textDim">AOR Unit (visibility)</label>
              <SearchableSelect
                options={unitOptions}
                value={flightForm.unit}
                onChange={(v) => setFlightForm({ ...flightForm, unit: v })}
                placeholder="Search units…"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">CAAP Flight Plan #</label>
                <input
                  value={flightForm.caap_flight_plan_number}
                  onChange={(e) => setFlightForm({ ...flightForm, caap_flight_plan_number: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">CAAP Aircraft Registration</label>
                <input
                  value={flightForm.caap_aircraft_registration}
                  onChange={(e) => setFlightForm({ ...flightForm, caap_aircraft_registration: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
                />
              </div>
            </div>

            <div>
              <label className="mb-1 block text-xs text-ops-textDim">CAAP Remarks</label>
              <textarea
                value={flightForm.caap_remarks}
                onChange={(e) => setFlightForm({ ...flightForm, caap_remarks: e.target.value })}
                rows={2}
                className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
              />
            </div>

            {flightFormError && <p className="text-xs text-ops-danger">{flightFormError}</p>}

            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={() => setShowFlightForm(false)} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-textDim">
                Cancel
              </button>
              <button type="submit" disabled={isSavingFlight} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg disabled:opacity-50">
                {isSavingFlight ? 'Saving…' : 'Save'}
              </button>
            </div>
          </form>
        </div>
      )}

      {detailFlight && <FlightDetailModal flight={detailFlight} onClose={() => setDetailFlight(null)} />}

      {pendingFlightAction && (
        <ConfirmDialog
          title={
            pendingFlightAction.type === 'depart' ? 'Mark Flight Departed'
              : pendingFlightAction.type === 'arrive' ? 'Mark Flight Arrived'
              : 'Cancel Flight'
          }
          message={
            pendingFlightAction.type === 'depart'
              ? `Record actual departure for ${pendingFlightAction.flight.flight_number} now?`
              : pendingFlightAction.type === 'arrive'
              ? `Record actual arrival for ${pendingFlightAction.flight.flight_number} now?`
              : `Cancel flight ${pendingFlightAction.flight.flight_number}? This cannot be undone from this screen.`
          }
          danger={pendingFlightAction.type === 'cancel'}
          isBusy={isActionBusy}
          onConfirm={runPendingFlightAction}
          onCancel={() => setPendingFlightAction(null)}
        />
      )}

      {pendingAircraftArchive && (
        <ConfirmDialog
          title="Archive Aircraft"
          message={`Archive ${pendingAircraftArchive.tail_number}? It will be hidden from the active registry.`}
          danger
          isBusy={isActionBusy}
          onConfirm={runAircraftArchive}
          onCancel={() => setPendingAircraftArchive(null)}
        />
      )}
    </div>
  );
}
