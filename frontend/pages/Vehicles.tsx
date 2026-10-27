import { FormEvent, useEffect, useState } from 'react';

import { missionsApi, personnelApi, vehiclesApi } from '@/api/endpoints';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import OperationalMap from '@/components/common/OperationalMap';
import SearchableSelect from '@/components/common/SearchableSelect';
import VehicleMaintenance from '@/components/vehicles/VehicleMaintenance';
import VehicleTrackModal from '@/components/vehicles/VehicleTrackModal';
import VehicleTrips from '@/components/vehicles/VehicleTrips';
import { useAuth } from '@/contexts/AuthContext';
import { useToast } from '@/contexts/ToastContext';
import type { MapPoint, MissionListItem, PersonnelListItem, VehicleDetail, VehicleListItem, VehicleStatus } from '@/types';

const STATUS_BADGE: Record<VehicleStatus, string> = {
  AVAILABLE: 'bg-ops-success/10 text-ops-success',
  ON_MISSION: 'bg-ops-accent/10 text-ops-accent',
  MAINTENANCE: 'bg-ops-warning/10 text-ops-warning',
  OUT_OF_SERVICE: 'bg-ops-danger/10 text-ops-danger',
};

const STATUS_OPTIONS: (VehicleStatus | 'ALL')[] = ['ALL', 'AVAILABLE', 'ON_MISSION', 'MAINTENANCE', 'OUT_OF_SERVICE'];
const FUEL_TYPES = ['DIESEL', 'GASOLINE', 'ELECTRIC', 'HYBRID'];

const emptyForm = {
  plate_number: '', make: '', model: '', vehicle_type: '', year: '', capacity: '',
  fuel_type: '', assigned_driver: null as string | null, assigned_mission: null as string | null,
  odometer_km: '', status: '' as VehicleStatus | '',
};

type VehicleTab = 'registry' | 'trips' | 'maintenance';

const VEHICLE_TABS: { key: VehicleTab; label: string }[] = [
  { key: 'registry', label: 'Vehicle Registry' },
  { key: 'trips', label: 'Trip History' },
  { key: 'maintenance', label: 'Maintenance Records' },
];

export default function Vehicles() {
  const [tab, setTab] = useState<VehicleTab>('registry');

  return (
    <div className="space-y-4">
      <div className="flex gap-2 border-b border-ops-border pb-3">
        {VEHICLE_TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
              tab === t.key ? 'border-ops-accent bg-ops-accent/10 text-ops-accent' : 'border-ops-border text-ops-textDim hover:text-ops-text'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'registry' && <VehicleRegistry />}
      {tab === 'trips' && <VehicleTrips />}
      {tab === 'maintenance' && <VehicleMaintenance />}
    </div>
  );
}

function VehicleRegistry() {
  const { can } = useAuth();
  const { showSuccess, showError } = useToast();

  const [vehicles, setVehicles] = useState<VehicleListItem[]>([]);
  const [personnel, setPersonnel] = useState<PersonnelListItem[]>([]);
  const [missions, setMissions] = useState<MissionListItem[]>([]);
  const [statusFilter, setStatusFilter] = useState<VehicleStatus | 'ALL'>('ALL');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [isSaving, setIsSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const [pendingAction, setPendingAction] = useState<
    { type: 'dispatch' | 'return' | 'archive'; vehicle: VehicleListItem } | null
  >(null);
  const [isActionBusy, setIsActionBusy] = useState(false);
  const [trackingVehicle, setTrackingVehicle] = useState<VehicleListItem | null>(null);

  const canCreate = can('VEHICLES', 'CREATE');
  const canEdit = can('VEHICLES', 'EDIT');
  const canDelete = can('VEHICLES', 'DELETE');
  const canDispatch = can('VEHICLES', 'DISPATCH');
  const canReturn = can('VEHICLES', 'RETURN');

  const loadVehicles = () =>
    vehiclesApi
      .list(statusFilter === 'ALL' ? undefined : { status: statusFilter })
      .then((data) => setVehicles(data.results))
      .catch(() => setError('Unable to load vehicle registry.'));

  useEffect(() => {
    setIsLoading(true);
    loadVehicles().finally(() => setIsLoading(false));
  }, [statusFilter]);

  useEffect(() => {
    personnelApi.list({ page_size: 200 }).then((d) => setPersonnel(d.results)).catch(() => {});
    missionsApi.list({ page_size: 200 }).then((d) => setMissions(d.results)).catch(() => {});
  }, []);

  const mapPoints: MapPoint[] = vehicles
    .filter((v) => v.last_known_location)
    .map((v) => ({
      type: 'vehicle',
      label: `${v.plate_number}${v.driver_name ? ` — ${v.driver_name}` : ''}`,
      lat: v.last_known_location!.lat,
      lng: v.last_known_location!.lng,
    }));

  const openCreateForm = () => {
    setEditingId(null);
    setForm(emptyForm);
    setFormError('');
    setShowForm(true);
  };

  const openEditForm = async (vehicle: VehicleListItem) => {
    try {
      const detail: VehicleDetail = await vehiclesApi.get(vehicle.id);
      setEditingId(vehicle.id);
      setForm({
        plate_number: detail.plate_number, make: detail.make, model: detail.model,
        vehicle_type: detail.vehicle_type, year: detail.year?.toString() ?? '',
        capacity: detail.capacity?.toString() ?? '', fuel_type: detail.fuel_type,
        assigned_driver: detail.assigned_driver, assigned_mission: detail.assigned_mission,
        odometer_km: detail.odometer_km?.toString() ?? '', status: detail.status,
      });
      setFormError('');
      setShowForm(true);
    } catch {
      showError('Unable to load vehicle details.');
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setFormError('');

    const payload = {
      plate_number: form.plate_number, make: form.make, model: form.model, vehicle_type: form.vehicle_type,
      year: form.year ? Number(form.year) : null, capacity: form.capacity ? Number(form.capacity) : null,
      fuel_type: form.fuel_type || undefined, assigned_driver: form.assigned_driver,
      assigned_mission: form.assigned_mission,
      ...(form.odometer_km !== '' ? { odometer_km: Number(form.odometer_km) } : {}),
      ...(editingId && form.status ? { status: form.status } : {}),
    };

    try {
      if (editingId) {
        await vehiclesApi.update(editingId, payload);
        showSuccess(`Vehicle ${form.plate_number} updated successfully.`);
      } else {
        await vehiclesApi.create(payload);
        showSuccess(`Vehicle ${form.plate_number} registered successfully.`);
      }
      setShowForm(false);
      await loadVehicles();
    } catch (err: any) {
      const data = err?.response?.data;
      const message = data ? Object.values(data).flat().join(' ') : 'Unable to save record. Please check the required fields.';
      setFormError(message);
    } finally {
      setIsSaving(false);
    }
  };

  const runPendingAction = async () => {
    if (!pendingAction) return;
    setIsActionBusy(true);
    try {
      if (pendingAction.type === 'dispatch') {
        await vehiclesApi.dispatch(pendingAction.vehicle.id);
        showSuccess(`Vehicle ${pendingAction.vehicle.plate_number} successfully dispatched.`);
      } else if (pendingAction.type === 'return') {
        await vehiclesApi.returnVehicle(pendingAction.vehicle.id);
        showSuccess(`Vehicle ${pendingAction.vehicle.plate_number} marked as returned.`);
      } else {
        await vehiclesApi.archive(pendingAction.vehicle.id);
        showSuccess(`Vehicle ${pendingAction.vehicle.plate_number} archived.`);
      }
      setPendingAction(null);
      await loadVehicles();
    } catch (err: any) {
      showError(err?.response?.data?.detail ?? 'You do not have permission to perform this action.');
    } finally {
      setIsActionBusy(false);
    }
  };

  const driverOptions = personnel.map((p) => ({ value: p.id, label: p.full_name, sublabel: p.service_number }));
  const missionOptions = missions.map((m) => ({ value: m.id, label: m.name }));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          {STATUS_OPTIONS.map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
                statusFilter === s
                  ? 'border-ops-accent bg-ops-accent/10 text-ops-accent'
                  : 'border-ops-border text-ops-textDim hover:text-ops-text'
              }`}
            >
              {s.replace('_', ' ')}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-ops-textDim">{vehicles.length} vehicle(s)</span>
          {canCreate && (
            <button
              onClick={openCreateForm}
              className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg"
            >
              + Add Vehicle
            </button>
          )}
        </div>
      </div>

      {error && <p className="text-sm text-ops-danger">{error}</p>}

      <OperationalMap points={mapPoints} height="300px" />

      <div className="ops-card overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-ops-panelLight text-xs uppercase tracking-wider text-ops-textDim">
            <tr>
              <th className="px-4 py-3">Plate #</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Driver</th>
              <th className="px-4 py-3">Mission</th>
              <th className="px-4 py-3">Odometer</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Last Update</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {!isLoading && vehicles.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-6 text-center text-ops-textDim">
                  No vehicles found.
                </td>
              </tr>
            )}
            {vehicles.map((v) => (
              <tr key={v.id} className="border-t border-ops-border hover:bg-ops-panelLight/50">
                <td className="px-4 py-3 font-mono text-xs">{v.plate_number}</td>
                <td className="px-4 py-3">{v.vehicle_type || '—'}</td>
                <td className="px-4 py-3">{v.driver_name ?? '—'}</td>
                <td className="px-4 py-3">{v.mission_name ?? '—'}</td>
                <td className="px-4 py-3 font-mono text-xs text-ops-textDim">{v.odometer_km.toLocaleString()} km</td>
                <td className="px-4 py-3">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_BADGE[v.status]}`}>
                    {v.status.replace('_', ' ')}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs text-ops-textDim">
                  {v.last_location_updated_at ? new Date(v.last_location_updated_at).toLocaleString() : '—'}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-2 whitespace-nowrap">
                    <button onClick={() => setTrackingVehicle(v)} className="text-xs font-medium text-ops-textDim hover:text-ops-accent">
                      Track
                    </button>
                    {canEdit && (
                      <button onClick={() => openEditForm(v)} className="text-xs font-medium text-ops-textDim hover:text-ops-text">
                        Edit
                      </button>
                    )}
                    {canDispatch && v.status === 'AVAILABLE' && (
                      <button
                        onClick={() => setPendingAction({ type: 'dispatch', vehicle: v })}
                        className="text-xs font-medium text-ops-accent hover:underline"
                      >
                        Dispatch
                      </button>
                    )}
                    {canReturn && v.status === 'ON_MISSION' && (
                      <button
                        onClick={() => setPendingAction({ type: 'return', vehicle: v })}
                        className="text-xs font-medium text-ops-success hover:underline"
                      >
                        Return
                      </button>
                    )}
                    {canDelete && (
                      <button
                        onClick={() => setPendingAction({ type: 'archive', vehicle: v })}
                        className="text-xs font-medium text-ops-danger hover:underline"
                      >
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

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <form onSubmit={handleSubmit} className="ops-card w-full max-w-lg space-y-3 p-6">
            <p className="ops-label">{editingId ? 'Edit Vehicle' : 'Add Vehicle'}</p>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Plate Number *</label>
                <input
                  required
                  value={form.plate_number}
                  onChange={(e) => setForm({ ...form, plate_number: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Vehicle Type</label>
                <input
                  value={form.vehicle_type}
                  onChange={(e) => setForm({ ...form, vehicle_type: e.target.value })}
                  placeholder="e.g. Truck, Sedan"
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Make</label>
                <input
                  value={form.make}
                  onChange={(e) => setForm({ ...form, make: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Model</label>
                <input
                  value={form.model}
                  onChange={(e) => setForm({ ...form, model: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Year</label>
                <input
                  type="number"
                  value={form.year}
                  onChange={(e) => setForm({ ...form, year: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Capacity</label>
                <input
                  type="number"
                  value={form.capacity}
                  onChange={(e) => setForm({ ...form, capacity: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Fuel Type</label>
                <select
                  value={form.fuel_type}
                  onChange={(e) => setForm({ ...form, fuel_type: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text"
                >
                  <option value="">— Select —</option>
                  {FUEL_TYPES.map((f) => (
                    <option key={f} value={f}>{f}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Odometer (km)</label>
                <input
                  type="number"
                  min={0}
                  value={form.odometer_km}
                  onChange={(e) => setForm({ ...form, odometer_km: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
                />
              </div>
              {editingId && (
                <div>
                  <label className="mb-1 block text-xs text-ops-textDim">Status</label>
                  <select
                    value={form.status}
                    onChange={(e) => setForm({ ...form, status: e.target.value as VehicleStatus })}
                    className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text"
                  >
                    {STATUS_OPTIONS.filter((s) => s !== 'ALL').map((s) => (
                      <option key={s} value={s}>{s.replace('_', ' ')}</option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            <div>
              <label className="mb-1 block text-xs text-ops-textDim">Driver</label>
              <SearchableSelect
                options={driverOptions}
                value={form.assigned_driver}
                onChange={(v) => setForm({ ...form, assigned_driver: v })}
                placeholder="Search personnel…"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs text-ops-textDim">Assigned Mission</label>
              <SearchableSelect
                options={missionOptions}
                value={form.assigned_mission}
                onChange={(v) => setForm({ ...form, assigned_mission: v })}
                placeholder="Search missions…"
              />
            </div>

            {formError && <p className="text-xs text-ops-danger">{formError}</p>}

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-textDim"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSaving}
                className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg disabled:opacity-50"
              >
                {isSaving ? 'Saving…' : 'Save'}
              </button>
            </div>
          </form>
        </div>
      )}

      {trackingVehicle && (
        <VehicleTrackModal
          vehicle={trackingVehicle}
          canReport={canEdit}
          onClose={() => setTrackingVehicle(null)}
          onReported={() => void loadVehicles()}
        />
      )}

      {pendingAction && (
        <ConfirmDialog
          title={
            pendingAction.type === 'dispatch' ? 'Dispatch Vehicle'
              : pendingAction.type === 'return' ? 'Return Vehicle'
              : 'Archive Vehicle'
          }
          message={
            pendingAction.type === 'dispatch'
              ? `Dispatch ${pendingAction.vehicle.plate_number}? Its status will change to ON MISSION.`
              : pendingAction.type === 'return'
              ? `Mark ${pendingAction.vehicle.plate_number} as returned? Its status will change to AVAILABLE.`
              : `Archive ${pendingAction.vehicle.plate_number}? It will be hidden from the active registry.`
          }
          danger={pendingAction.type === 'archive'}
          isBusy={isActionBusy}
          onConfirm={runPendingAction}
          onCancel={() => setPendingAction(null)}
        />
      )}
    </div>
  );
}
