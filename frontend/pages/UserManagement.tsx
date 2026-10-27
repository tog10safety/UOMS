import { useCallback, useEffect, useMemo, useState } from 'react';

import { sectionsApi, unitsApi, usersApi } from '@/api/endpoints';
import { badgeClass } from '@/components/common/FormFields';
import ResourceManager, { ColumnDef, FieldDef } from '@/components/common/ResourceManager';
import { AUTHORITY_LABEL, AUTHORITY_OPTIONS, DESIGNATION_OPTIONS } from '@/components/mrm/MrmBadges';
import { useAuth } from '@/contexts/AuthContext';
import type { Section, Unit, User, UserRole } from '@/types';
import { formatDateTime } from '@/utils/errors';

const ROLE_OPTIONS: { value: UserRole; label: string }[] = [
  { value: 'ADMIN', label: 'System Administrator' },
  { value: 'COMMANDER', label: 'Unit Commander' },
  { value: 'STAFF', label: 'Staff Officer' },
  { value: 'OPERATOR', label: 'Operator / Data Entry' },
  { value: 'VIEWER', label: 'Read-only Viewer' },
];

export default function UserManagement() {
  const { user: currentUser, can, hasRole } = useAuth();
  const [units, setUnits] = useState<Unit[]>([]);
  const [sections, setSections] = useState<Section[]>([]);

  const canView = can('ADMINISTRATION', 'VIEW');

  useEffect(() => {
    if (!canView) return;
    unitsApi.list().then((d) => setUnits(d.results.filter((u) => u.is_active))).catch(() => {});
    sectionsApi.list({ page_size: 200 }).then((d) => setSections(d.results.filter((s) => s.is_active))).catch(() => {});
  }, [canView]);

  const load = useCallback((params: Record<string, string | number | boolean>) => usersApi.list(params).then((d) => d.results), []);

  const fields: FieldDef[] = useMemo(
    () => [
      { name: 'username', label: 'Username', type: 'text', required: true },
      { name: 'email', label: 'Email', type: 'email', required: true },
      { name: 'first_name', label: 'First Name', type: 'text' },
      { name: 'last_name', label: 'Last Name', type: 'text' },
      { name: 'role', label: 'Role', type: 'select', required: true, options: ROLE_OPTIONS, defaultValue: 'VIEWER' },
      { name: 'phone_number', label: 'Phone Number', type: 'text' },
      {
        name: 'mrm_authority', label: 'MRM authority', type: 'select', options: AUTHORITY_OPTIONS,
        help: 'What this user may do in Mission Risk Management. Blank = none (administrators always act as MRM Administrators).',
      },
      {
        name: 'mrm_designation', label: 'MRM decision designation', type: 'select', options: DESIGNATION_OPTIONS,
        help: 'The risk tier this user may sign approvals for. Independent of MRM authority.',
      },
      { name: 'unit', label: 'Unit / AOR', type: 'search', options: units.map((u) => ({ value: u.id, label: u.name, sublabel: u.code })), help: 'Drives which unit records this account can see.' },
      { name: 'section', label: 'Section', type: 'search', options: sections.map((s) => ({ value: s.id, label: s.name, sublabel: s.unit_name })) },
      {
        name: 'password', label: 'Initial Password', type: 'password', required: true, createOnly: true, span: 2,
        help: 'The user will be required to change this at first login.',
      },
      { name: 'is_active', label: 'Account is active', type: 'checkbox', defaultValue: true },
    ],
    [units, sections],
  );

  const columns: ColumnDef<User>[] = [
    { header: 'Username', render: (u) => u.username, className: 'font-mono text-xs' },
    { header: 'Full Name', render: (u) => u.full_name },
    { header: 'Email', render: (u) => u.email, className: 'text-ops-textDim' },
    { header: 'Role', render: (u) => <span className={`${badgeClass} bg-ops-accent/10 text-ops-accent`}>{u.role}</span> },
    { header: 'Unit', render: (u) => u.unit_name ?? '—' },
    {
      header: 'MRM',
      render: (u) => (
        <span className="text-xs">
          {AUTHORITY_LABEL[u.effective_mrm_authority] ?? <span className="text-ops-textDim">—</span>}
          {u.mrm_designation && <span className="text-ops-textDim"> · {u.mrm_designation.replace(/_/g, ' ').toLowerCase()}</span>}
          {!u.has_signature && u.effective_mrm_authority && <span className="ml-1 text-ops-warning" title="No signature uploaded">✎?</span>}
        </span>
      ),
    },
    { header: 'Last Login', render: (u) => formatDateTime(u.last_login), className: 'text-xs text-ops-textDim' },
  ];

  if (!canView && !hasRole('ADMIN')) {
    return (
      <div className="ops-card p-6 text-center text-sm text-ops-textDim">
        You need Administrator privileges to view user accounts.
      </div>
    );
  }

  return (
    <ResourceManager<User>
      noun="user account"
      addLabel="+ Add User"
      columns={columns}
      fields={fields}
      load={load}
      create={usersApi.create as (payload: unknown) => Promise<unknown>}
      update={usersApi.update as (id: string, payload: unknown) => Promise<unknown>}
      remove={usersApi.deactivate}
      removeVerb="Deactivate"
      canCreate={can('ADMINISTRATION', 'CREATE')}
      canEdit={can('ADMINISTRATION', 'EDIT')}
      canDelete={can('ADMINISTRATION', 'DELETE')}
      rowLabel={(u) => u.username}
      searchPlaceholder="Search username, name, email…"
      // An administrator must not lock themselves out of their own account.
      canDeleteRow={(u) => u.id !== currentUser?.id}
      extraRowActions={(u) => (u.id === currentUser?.id ? <span className="text-[10px] uppercase text-ops-textDim">You</span> : null)}
      formWidth="lg"
    />
  );
}
