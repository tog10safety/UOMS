import { useCallback, useEffect, useMemo, useState } from 'react';

import { missionsApi, personnelApi, vehiclesApi } from '@/api/endpoints';
import { badgeClass } from '@/components/common/FormFields';
import ResourceManager, { ColumnDef, FieldDef } from '@/components/common/ResourceManager';
import { useAuth } from '@/contexts/AuthContext';
import type { MissionListItem, PersonnelListItem, Trip, VehicleListItem } from '@/types';
import { formatDateTime } from '@/utils/errors';

const STATUS_BADGE: Record<Trip['status'], string> = {
  ONGOING: 'bg-ops-accent/10 text-ops-accent',
  COMPLETED: 'bg-ops-success/10 text-ops-success',
  CANCELLED: 'bg-ops-danger/10 text-ops-danger',
};

export default function VehicleTrips() {
  const { can } = useAuth();
  const [vehicles, setVehicles] = useState<VehicleListItem[]>([]);
  const [personnel, setPersonnel] = useState<PersonnelListItem[]>([]);
  const [missions, setMissions] = useState<MissionListItem[]>([]);
  const [statusFilter, setStatusFilter] = useState('');

  useEffect(() => {
    vehiclesApi.list({ page_size: 200 }).then((d) => setVehicles(d.results)).catch(() => {});
    personnelApi.list({ page_size: 200 }).then((d) => setPersonnel(d.results)).catch(() => {});
    missionsApi.list({ page_size: 200 }).then((d) => setMissions(d.results)).catch(() => {});
  }, []);

  const load = useCallback((params: Record<string, string | number | boolean>) => vehiclesApi.trips({ ordering: '-start_time', ...params }).then((d) => d.results), []);

  const fields: FieldDef[] = useMemo(
    () => [
      { name: 'vehicle', label: 'Vehicle', type: 'search', required: true, options: vehicles.map((v) => ({ value: v.id, label: v.plate_number, sublabel: v.vehicle_type })) },
      { name: 'driver', label: 'Driver', type: 'search', required: true, options: personnel.map((p) => ({ value: p.id, label: p.full_name, sublabel: p.service_number })) },
      { name: 'origin', label: 'Origin', type: 'text', required: true },
      { name: 'destination', label: 'Destination', type: 'text', required: true },
      { name: 'start_time', label: 'Start Time', type: 'datetime', required: true },
      { name: 'end_time', label: 'End Time', type: 'datetime' },
      { name: 'start_odometer_km', label: 'Start Odometer (km)', type: 'number', required: true },
      { name: 'end_odometer_km', label: 'End Odometer (km)', type: 'number' },
      {
        name: 'status', label: 'Status', type: 'select', required: true, defaultValue: 'ONGOING',
        options: [{ value: 'ONGOING', label: 'Ongoing' }, { value: 'COMPLETED', label: 'Completed' }, { value: 'CANCELLED', label: 'Cancelled' }],
      },
      { name: 'mission', label: 'Mission', type: 'search', options: missions.map((m) => ({ value: m.id, label: m.name })) },
      { name: 'purpose', label: 'Purpose', type: 'text', span: 2 },
      { name: 'remarks', label: 'Remarks', type: 'textarea' },
    ],
    [vehicles, personnel, missions],
  );

  const columns: ColumnDef<Trip>[] = [
    { header: 'Vehicle', render: (t) => t.vehicle_plate, className: 'font-mono text-xs' },
    { header: 'Route', render: (t) => `${t.origin} → ${t.destination}` },
    { header: 'Driver', render: (t) => t.driver_name },
    { header: 'Started', render: (t) => formatDateTime(t.start_time), className: 'text-xs text-ops-textDim' },
    { header: 'Ended', render: (t) => formatDateTime(t.end_time), className: 'text-xs text-ops-textDim' },
    { header: 'Distance', render: (t) => (t.distance_km != null ? `${t.distance_km.toLocaleString()} km` : '—'), className: 'font-mono text-xs' },
    { header: 'Status', render: (t) => <span className={`${badgeClass} ${STATUS_BADGE[t.status]}`}>{t.status}</span> },
  ];

  return (
    <ResourceManager<Trip>
      noun="trip"
      addLabel="+ Log Trip"
      columns={columns}
      fields={fields}
      load={load}
      create={vehiclesApi.createTrip}
      update={vehiclesApi.updateTrip}
      remove={vehiclesApi.deleteTrip}
      removeVerb="Delete"
      supportsArchive={false}
      canCreate={can('VEHICLES', 'CREATE')}
      canEdit={can('VEHICLES', 'EDIT')}
      canDelete={can('VEHICLES', 'DELETE')}
      rowLabel={(t) => `the ${t.vehicle_plate} trip to ${t.destination}`}
      extraParams={statusFilter ? { status: statusFilter } : undefined}
      toolbar={
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-md border border-ops-border bg-ops-panelLight px-2 py-1.5 text-xs text-ops-text"
        >
          <option value="">All statuses</option>
          <option value="ONGOING">Ongoing</option>
          <option value="COMPLETED">Completed</option>
          <option value="CANCELLED">Cancelled</option>
        </select>
      }
      formWidth="lg"
    />
  );
}
