import { useCallback, useEffect, useMemo, useState } from 'react';

import { personnelApi, positionsApi, qualificationsApi, ranksApi, sectionsApi, unitsApi, usersApi } from '@/api/endpoints';
import ResourceManager, { ColumnDef, FieldDef } from '@/components/common/ResourceManager';
import { badgeClass } from '@/components/common/FormFields';
import { useAuth } from '@/contexts/AuthContext';
import type { PersonnelListItem, PersonnelStatus, Position, Qualification, Rank, Section, Unit, User } from '@/types';

const STATUS_BADGE: Record<string, string> = {
  ACTIVE: 'bg-ops-success/10 text-ops-success',
  ON_LEAVE: 'bg-ops-warning/10 text-ops-warning',
  DEPLOYED: 'bg-ops-accent/10 text-ops-accent',
  TRAINING: 'bg-ops-warning/10 text-ops-warning',
  MEDICAL: 'bg-ops-danger/10 text-ops-danger',
  SEPARATED: 'bg-ops-textDim/10 text-ops-textDim',
};

const STATUS_OPTIONS: { value: PersonnelStatus; label: string }[] = [
  { value: 'ACTIVE', label: 'Active' },
  { value: 'ON_LEAVE', label: 'On Leave' },
  { value: 'DEPLOYED', label: 'Deployed' },
  { value: 'TRAINING', label: 'Training' },
  { value: 'MEDICAL', label: 'Medical' },
  { value: 'SEPARATED', label: 'Separated' },
];

type Tab = 'records' | 'ranks' | 'sections' | 'positions' | 'qualifications';

const TABS: { key: Tab; label: string }[] = [
  { key: 'records', label: 'Personnel Records' },
  { key: 'ranks', label: 'Ranks' },
  { key: 'sections', label: 'Sections' },
  { key: 'positions', label: 'Positions' },
  { key: 'qualifications', label: 'Qualifications' },
];

export default function Personnel() {
  const { can } = useAuth();
  const [tab, setTab] = useState<Tab>('records');

  const [ranks, setRanks] = useState<Rank[]>([]);
  const [units, setUnits] = useState<Unit[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [qualifications, setQualifications] = useState<Qualification[]>([]);
  const [accounts, setAccounts] = useState<User[]>([]);
  // Bumped whenever reference data is edited so the dropdowns stay current.
  const [lookupVersion, setLookupVersion] = useState(0);

  useEffect(() => {
    ranksApi.list({ page_size: 200 }).then((d) => setRanks(d.results.filter((r) => r.is_active))).catch(() => {});
    unitsApi.list().then((d) => setUnits(d.results.filter((u) => u.is_active))).catch(() => {});
    positionsApi.list({ page_size: 200 }).then((d) => setPositions(d.results.filter((p) => p.is_active))).catch(() => {});
    qualificationsApi.list({ page_size: 200 }).then((d) => setQualifications(d.results.filter((q) => q.is_active))).catch(() => {});
    // Only administrators/commanders may read accounts; failure just means no "linked account" picker.
    usersApi.list({ page_size: 200 }).then((d) => setAccounts(d.results)).catch(() => {});
  }, [lookupVersion]);

  const canCreate = can('PERSONNEL', 'CREATE');
  const canEdit = can('PERSONNEL', 'EDIT');
  const canDelete = can('PERSONNEL', 'DELETE');
  const bump = () => setLookupVersion((v) => v + 1);

  // ---- Personnel records -------------------------------------------------
  const loadRecords = useCallback((params: Record<string, string | number | boolean>) => personnelApi.list(params).then((d) => d.results), []);

  const recordColumns: ColumnDef<PersonnelListItem>[] = [
    { header: 'Service #', render: (p) => p.service_number, className: 'font-mono text-xs text-ops-textDim' },
    { header: 'Name', render: (p) => p.full_name, className: 'font-medium text-ops-text' },
    { header: 'Rank', render: (p) => p.rank_abbreviation },
    { header: 'Unit', render: (p) => p.unit_name },
    { header: 'Position', render: (p) => p.position_title ?? '—' },
    {
      header: 'Status',
      render: (p) => <span className={`${badgeClass} ${STATUS_BADGE[p.status] ?? ''}`}>{p.status.replace('_', ' ')}</span>,
    },
  ];

  const recordFields: FieldDef[] = useMemo(
    () => [
      { name: 'service_number', label: 'Service Number', type: 'text', required: true },
      { name: 'status', label: 'Status', type: 'select', options: STATUS_OPTIONS, defaultValue: 'ACTIVE', required: true },
      { name: 'first_name', label: 'First Name', type: 'text', required: true },
      { name: 'last_name', label: 'Last Name', type: 'text', required: true },
      { name: 'middle_name', label: 'Middle Name', type: 'text' },
      { name: 'rank', label: 'Rank', type: 'search', required: true, options: ranks.map((r) => ({ value: r.id, label: r.name, sublabel: r.abbreviation })) },
      { name: 'unit', label: 'Unit', type: 'search', required: true, options: units.map((u) => ({ value: u.id, label: u.name, sublabel: u.code })) },
      { name: 'position', label: 'Position', type: 'search', options: positions.map((p) => ({ value: p.id, label: p.title })) },
      { name: 'date_enlisted', label: 'Date Enlisted', type: 'date' },
      { name: 'date_of_birth', label: 'Date of Birth', type: 'date' },
      { name: 'contact_number', label: 'Contact Number', type: 'text' },
      { name: 'email', label: 'Email', type: 'email' },
      { name: 'qualifications', label: 'Qualifications', type: 'multiselect', options: qualifications.map((q) => ({ value: q.id, label: q.name })) },
      {
        name: 'linked_account', label: 'Linked User Account', type: 'search', span: 2,
        options: accounts.map((a) => ({ value: a.id, label: a.username, sublabel: a.full_name })),
        help: 'Optional — ties this record to a login account (one record per account).',
      },
      { name: 'photo', label: 'Photo', type: 'file' },
      { name: 'remarks', label: 'Remarks', type: 'textarea' },
    ],
    [ranks, units, positions, qualifications, accounts],
  );

  // ---- Reference tables --------------------------------------------------
  const rankFields: FieldDef[] = [
    { name: 'name', label: 'Rank Name', type: 'text', required: true },
    { name: 'abbreviation', label: 'Abbreviation', type: 'text', required: true },
    { name: 'order', label: 'Seniority Order', type: 'number', required: true, defaultValue: '0', help: 'Lower number = more senior.' },
  ];

  const sectionFields: FieldDef[] = useMemo(
    () => [
      { name: 'name', label: 'Section Name', type: 'text', required: true },
      { name: 'code', label: 'Code', type: 'text' },
      { name: 'unit', label: 'Unit', type: 'search', required: true, span: 2, options: units.map((u) => ({ value: u.id, label: u.name, sublabel: u.code })) },
      { name: 'description', label: 'Description', type: 'textarea' },
    ],
    [units],
  );

  const positionFields: FieldDef[] = [
    { name: 'title', label: 'Title', type: 'text', required: true, span: 2 },
    { name: 'description', label: 'Description', type: 'textarea' },
  ];

  const qualificationFields: FieldDef[] = [
    { name: 'name', label: 'Qualification', type: 'text', required: true, span: 2 },
    { name: 'validity_period_days', label: 'Validity (days)', type: 'number', help: 'Leave blank if it never expires.' },
    { name: 'description', label: 'Description', type: 'textarea' },
  ];

  const loadRanks = useCallback(() => ranksApi.list({ page_size: 200, ordering: 'order' }).then((d) => d.results), []);
  const loadSections = useCallback((p: Record<string, string | number | boolean>) => sectionsApi.list(p).then((d) => d.results), []);
  const loadPositions = useCallback((p: Record<string, string | number | boolean>) => positionsApi.list(p).then((d) => d.results), []);
  const loadQualifications = useCallback((p: Record<string, string | number | boolean>) => qualificationsApi.list(p).then((d) => d.results), []);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {TABS.map((t) => (
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

      {tab === 'records' && (
        <ResourceManager<PersonnelListItem>
          noun="personnel record"
          addLabel="+ Add Personnel"
          columns={recordColumns}
          fields={recordFields}
          load={loadRecords}
          create={personnelApi.create}
          update={personnelApi.update}
          remove={personnelApi.archive}
          fetchForEdit={(row) => personnelApi.get(row.id)}
          canCreate={canCreate}
          canEdit={canEdit}
          canDelete={canDelete}
          rowLabel={(p) => p.full_name}
          searchPlaceholder="Search by name, service number, email…"
          formWidth="lg"
        />
      )}

      {tab === 'ranks' && (
        <ResourceManager<Rank>
          noun="rank"
          columns={[
            { header: 'Order', render: (r) => r.order, className: 'font-mono text-xs text-ops-textDim' },
            { header: 'Rank', render: (r) => r.name, className: 'font-medium text-ops-text' },
            { header: 'Abbreviation', render: (r) => r.abbreviation },
          ]}
          fields={rankFields}
          load={loadRanks}
          create={ranksApi.create}
          update={ranksApi.update}
          remove={ranksApi.remove}
          canCreate={canCreate}
          canEdit={canEdit}
          canDelete={canDelete}
          rowLabel={(r) => r.name}
          onChanged={bump}
        />
      )}

      {tab === 'sections' && (
        <ResourceManager<Section>
          noun="section"
          columns={[
            { header: 'Section', render: (s) => s.name, className: 'font-medium text-ops-text' },
            { header: 'Code', render: (s) => s.code || '—', className: 'font-mono text-xs' },
            { header: 'Unit', render: (s) => s.unit_name },
            { header: 'Description', render: (s) => s.description || '—', className: 'text-ops-textDim' },
          ]}
          fields={sectionFields}
          load={loadSections}
          create={sectionsApi.create}
          update={sectionsApi.update}
          remove={sectionsApi.remove}
          canCreate={canCreate}
          canEdit={canEdit}
          canDelete={canDelete}
          rowLabel={(s) => s.name}
          searchPlaceholder="Search sections…"
          onChanged={bump}
        />
      )}

      {tab === 'positions' && (
        <ResourceManager<Position>
          noun="position"
          columns={[
            { header: 'Title', render: (p) => p.title, className: 'font-medium text-ops-text' },
            { header: 'Description', render: (p) => p.description || '—', className: 'text-ops-textDim' },
          ]}
          fields={positionFields}
          load={loadPositions}
          create={positionsApi.create}
          update={positionsApi.update}
          remove={positionsApi.remove}
          canCreate={canCreate}
          canEdit={canEdit}
          canDelete={canDelete}
          rowLabel={(p) => p.title}
          searchPlaceholder="Search positions…"
          onChanged={bump}
        />
      )}

      {tab === 'qualifications' && (
        <ResourceManager<Qualification>
          noun="qualification"
          columns={[
            { header: 'Qualification', render: (q) => q.name, className: 'font-medium text-ops-text' },
            { header: 'Validity', render: (q) => (q.validity_period_days ? `${q.validity_period_days} days` : 'No expiry') },
            { header: 'Description', render: (q) => q.description || '—', className: 'text-ops-textDim' },
          ]}
          fields={qualificationFields}
          load={loadQualifications}
          create={qualificationsApi.create}
          update={qualificationsApi.update}
          remove={qualificationsApi.remove}
          canCreate={canCreate}
          canEdit={canEdit}
          canDelete={canDelete}
          rowLabel={(q) => q.name}
          searchPlaceholder="Search qualifications…"
          onChanged={bump}
        />
      )}
    </div>
  );
}
