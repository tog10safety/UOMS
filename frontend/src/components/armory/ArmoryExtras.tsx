import { useCallback, useMemo } from 'react';

import { armoryApi } from '@/api/endpoints';
import { badgeClass } from '@/components/common/FormFields';
import RecordFormModal, { FieldDef } from '@/components/common/RecordForm';
import ResourceManager, { ColumnDef } from '@/components/common/ResourceManager';
import { useAuth } from '@/contexts/AuthContext';
import { useToast } from '@/contexts/ToastContext';
import type { AmmunitionIssuance, AmmunitionStock, ArmoryInspection, Firearm, InspectionResult, PersonnelListItem, Unit } from '@/types';
import { formatDateTime, toDatetimeLocal } from '@/utils/errors';

export type AmmoAction = { type: 'edit' | 'issue'; stock: AmmunitionStock };

interface ModalsProps {
  action: AmmoAction | null;
  units: Unit[];
  personnel: PersonnelListItem[];
  onClose: () => void;
  onDone: () => void;
}

/** Edit-stock and issue-ammunition dialogs launched from the ammunition table. */
export function AmmoActionModals({ action, units, personnel, onClose, onDone }: ModalsProps) {
  const { showSuccess } = useToast();
  if (!action) return null;

  if (action.type === 'edit') {
    const fields: FieldDef[] = [
      { name: 'ammunition_type', label: 'Ammunition Type', type: 'text', required: true },
      { name: 'lot_number', label: 'Lot Number', type: 'text' },
      { name: 'quantity_on_hand', label: 'Quantity on Hand', type: 'number', required: true },
      { name: 'unit_of_measure', label: 'Unit of Measure', type: 'text' },
      { name: 'storage_location', label: 'Storage Location', type: 'text' },
      { name: 'expiration_date', label: 'Expiration Date', type: 'date' },
      { name: 'unit', label: 'Unit', type: 'search', span: 2, options: units.map((u) => ({ value: u.id, label: u.name, sublabel: u.code })) },
    ];
    return (
      <RecordFormModal
        title="Edit Ammunition Stock"
        fields={fields}
        record={action.stock}
        onSubmit={async (body) => {
          await armoryApi.updateAmmunition(action.stock.id, body);
          showSuccess('Ammunition stock updated.');
          onDone();
        }}
        onClose={onClose}
      />
    );
  }

  const fields: FieldDef[] = [
    { name: 'issued_to', label: 'Issued To', type: 'search', required: true, span: 2, options: personnel.map((p) => ({ value: p.id, label: p.full_name, sublabel: p.service_number })) },
    { name: 'quantity', label: `Quantity (max ${action.stock.quantity_on_hand})`, type: 'number', required: true },
    { name: 'issue_date', label: 'Issue Date', type: 'datetime', required: true, defaultValue: toDatetimeLocal(new Date().toISOString()) },
    { name: 'purpose', label: 'Purpose', type: 'text', span: 2 },
    { name: 'remarks', label: 'Remarks', type: 'textarea' },
  ];
  return (
    <RecordFormModal
      title={`Issue ${action.stock.ammunition_type}`}
      fields={fields}
      submitLabel="Issue"
      transformPayload={(p) => ({ ...p, ammunition_stock: action.stock.id })}
      onSubmit={async (body) => {
        await armoryApi.issueAmmunition(body);
        showSuccess(`Issued ${(body as { quantity: number }).quantity} ${action.stock.unit_of_measure}.`);
        onDone();
      }}
      onClose={onClose}
    />
  );
}

const RESULT_BADGE: Record<InspectionResult, string> = {
  PASSED: 'bg-ops-success/10 text-ops-success',
  FAILED: 'bg-ops-danger/10 text-ops-danger',
  NEEDS_MAINTENANCE: 'bg-ops-warning/10 text-ops-warning',
};

interface PanelProps {
  firearms: Firearm[];
  personnel: PersonnelListItem[];
  onChanged: () => void;
  refreshKey: number;
}

export function InspectionsPanel({ firearms, personnel, onChanged, refreshKey }: PanelProps) {
  const { can } = useAuth();

  const fields: FieldDef[] = useMemo(
    () => [
      {
        name: 'firearm', label: 'Firearm', type: 'search', help: 'Leave blank for a general armory inspection.',
        options: firearms.map((f) => ({ value: f.id, label: f.serial_number, sublabel: f.firearm_type })),
      },
      { name: 'inspected_by', label: 'Inspected By', type: 'search', required: true, options: personnel.map((p) => ({ value: p.id, label: p.full_name, sublabel: p.service_number })) },
      { name: 'inspection_date', label: 'Inspection Date', type: 'date', required: true },
      {
        name: 'result', label: 'Result', type: 'select', required: true, defaultValue: 'PASSED',
        options: [{ value: 'PASSED', label: 'Passed' }, { value: 'FAILED', label: 'Failed' }, { value: 'NEEDS_MAINTENANCE', label: 'Needs Maintenance' }],
        help: 'Failed → firearm becomes UNSERVICEABLE; Needs Maintenance → IN REPAIR.',
      },
      { name: 'findings', label: 'Findings', type: 'textarea' },
    ],
    [firearms, personnel],
  );

  const load = useCallback(
    (params: Record<string, string | number | boolean>) => armoryApi.inspections({ ordering: '-inspection_date', ...params }).then((d) => d.results),
    [],
  );

  const columns: ColumnDef<ArmoryInspection>[] = [
    { header: 'Date', render: (i) => i.inspection_date, className: 'text-xs text-ops-textDim' },
    { header: 'Firearm', render: (i) => i.firearm_serial ?? 'General armory', className: 'font-mono text-xs' },
    { header: 'Inspector', render: (i) => i.inspected_by_name },
    { header: 'Result', render: (i) => <span className={`${badgeClass} ${RESULT_BADGE[i.result]}`}>{i.result.replace('_', ' ')}</span> },
    { header: 'Findings', render: (i) => i.findings || '—', className: 'max-w-xs text-xs text-ops-textDim' },
  ];

  return (
    <ResourceManager<ArmoryInspection>
      title="Armory Inspections"
      noun="inspection"
      addLabel="+ Record Inspection"
      columns={columns}
      fields={fields}
      load={load}
      create={armoryApi.createInspection}
      update={armoryApi.updateInspection}
      remove={armoryApi.deleteInspection}
      removeVerb="Delete"
      supportsArchive={false}
      canCreate={can('ARMORY', 'CREATE')}
      canEdit={can('ARMORY', 'EDIT')}
      canDelete={can('ARMORY', 'DELETE')}
      rowLabel={(i) => `the ${i.inspection_date} inspection`}
      onChanged={onChanged}
      refreshKey={refreshKey}
    />
  );
}

/** Read-only ledger of ammunition issuances (issuing is done from the stock table). */
export function AmmoIssuancesPanel({ refreshKey }: { refreshKey: number }) {
  const load = useCallback(
    (params: Record<string, string | number | boolean>) => armoryApi.ammunitionIssuances({ ordering: '-issue_date', ...params }).then((d) => d.results),
    [],
  );
  const columns: ColumnDef<AmmunitionIssuance>[] = [
    { header: 'Issued', render: (i) => formatDateTime(i.issue_date), className: 'text-xs text-ops-textDim' },
    { header: 'Ammunition', render: (i) => i.ammunition_type },
    { header: 'Qty', render: (i) => i.quantity.toLocaleString(), className: 'font-mono text-xs' },
    { header: 'Issued To', render: (i) => i.issued_to_name },
    { header: 'Purpose', render: (i) => i.purpose || '—', className: 'text-xs text-ops-textDim' },
  ];
  return (
    <ResourceManager<AmmunitionIssuance>
      title="Ammunition Issuance Log"
      noun="ammunition issuance"
      columns={columns}
      fields={[]}
      load={load}
      supportsArchive={false}
      rowLabel={(i) => `${i.quantity} x ${i.ammunition_type}`}
      refreshKey={refreshKey}
    />
  );
}
