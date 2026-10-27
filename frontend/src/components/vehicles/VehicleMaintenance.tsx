import { useCallback, useEffect, useMemo, useState } from 'react';

import { vehiclesApi } from '@/api/endpoints';
import ResourceManager, { ColumnDef, FieldDef } from '@/components/common/ResourceManager';
import { useAuth } from '@/contexts/AuthContext';
import type { VehicleListItem, VehicleMaintenanceRecord } from '@/types';

const TYPE_OPTIONS = [
  { value: 'PREVENTIVE', label: 'Preventive Maintenance' },
  { value: 'REPAIR', label: 'Repair' },
  { value: 'INSPECTION', label: 'Inspection' },
  { value: 'TIRE_CHANGE', label: 'Tire Change' },
  { value: 'OIL_CHANGE', label: 'Oil Change' },
  { value: 'OTHER', label: 'Other' },
];

export default function VehicleMaintenance() {
  const { can } = useAuth();
  const [vehicles, setVehicles] = useState<VehicleListItem[]>([]);
  const [vehicleFilter, setVehicleFilter] = useState('');

  useEffect(() => {
    vehiclesApi.list({ page_size: 200 }).then((d) => setVehicles(d.results)).catch(() => {});
  }, []);

  const load = useCallback(
    (params: Record<string, string | number | boolean>) => vehiclesApi.maintenanceRecords({ ordering: '-service_date', ...params }).then((d) => d.results),
    [],
  );

  const fields: FieldDef[] = useMemo(
    () => [
      { name: 'vehicle', label: 'Vehicle', type: 'search', required: true, options: vehicles.map((v) => ({ value: v.id, label: v.plate_number, sublabel: v.vehicle_type })) },
      { name: 'maintenance_type', label: 'Type', type: 'select', required: true, options: TYPE_OPTIONS, defaultValue: 'PREVENTIVE' },
      { name: 'service_date', label: 'Service Date', type: 'date', required: true },
      { name: 'next_due_date', label: 'Next Due Date', type: 'date' },
      { name: 'performed_by', label: 'Performed By', type: 'text', placeholder: 'Shop / technician' },
      { name: 'cost', label: 'Cost', type: 'number', step: '0.01' },
      { name: 'odometer_at_service_km', label: 'Odometer at Service (km)', type: 'number', span: 2 },
      {
        name: 'description', label: 'Description', type: 'textarea',
        help: 'Logging a Repair or Preventive record moves an AVAILABLE vehicle to MAINTENANCE status.',
      },
    ],
    [vehicles],
  );

  const columns: ColumnDef<VehicleMaintenanceRecord>[] = [
    { header: 'Vehicle', render: (m) => m.vehicle_plate, className: 'font-mono text-xs' },
    { header: 'Type', render: (m) => m.maintenance_type.replace('_', ' ') },
    { header: 'Service Date', render: (m) => m.service_date, className: 'text-xs text-ops-textDim' },
    { header: 'Next Due', render: (m) => m.next_due_date ?? '—', className: 'text-xs text-ops-textDim' },
    { header: 'Performed By', render: (m) => m.performed_by || '—' },
    { header: 'Cost', render: (m) => (m.cost ? Number(m.cost).toLocaleString(undefined, { minimumFractionDigits: 2 }) : '—'), className: 'font-mono text-xs' },
    { header: 'Description', render: (m) => m.description || '—', className: 'max-w-xs text-xs text-ops-textDim' },
  ];

  return (
    <ResourceManager<VehicleMaintenanceRecord>
      noun="maintenance record"
      addLabel="+ Log Maintenance"
      columns={columns}
      fields={fields}
      load={load}
      create={vehiclesApi.createMaintenanceRecord}
      update={vehiclesApi.updateMaintenanceRecord}
      remove={vehiclesApi.deleteMaintenanceRecord}
      removeVerb="Delete"
      supportsArchive={false}
      canCreate={can('VEHICLES', 'CREATE')}
      canEdit={can('VEHICLES', 'EDIT')}
      canDelete={can('VEHICLES', 'DELETE')}
      rowLabel={(m) => `the ${m.vehicle_plate} ${m.maintenance_type.toLowerCase().replace('_', ' ')} record`}
      extraParams={vehicleFilter ? { vehicle: vehicleFilter } : undefined}
      toolbar={
        <select
          value={vehicleFilter}
          onChange={(e) => setVehicleFilter(e.target.value)}
          className="rounded-md border border-ops-border bg-ops-panelLight px-2 py-1.5 text-xs text-ops-text"
        >
          <option value="">All vehicles</option>
          {vehicles.map((v) => (
            <option key={v.id} value={v.id}>{v.plate_number}</option>
          ))}
        </select>
      }
    />
  );
}
