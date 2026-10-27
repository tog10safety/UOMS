import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { missionsApi, personnelApi, unitsApi } from '@/api/endpoints';
import { mrmApi } from '@/api/mrmApi';
import { badgeClass } from '@/components/common/FormFields';
import ResourceManager, { ColumnDef } from '@/components/common/ResourceManager';
import RiskLevelBadge from '@/components/common/RiskLevelBadge';
import { StageBadge } from '@/components/mrm/MrmBadges';
import { buildMissionFields } from '@/components/missions/missionFields';
import { useAuth } from '@/contexts/AuthContext';
import type {
  MissionApprovalLogEntry, MissionListItem, MissionStatus, PersonnelListItem, RiskReviewStatus, Unit,
} from '@/types';
import { formatDateTime } from '@/utils/errors';

const STATUS_BADGE: Record<MissionStatus, string> = {
  PLANNED: 'bg-ops-warning/10 text-ops-warning',
  APPROVED: 'bg-ops-accent/10 text-ops-accent',
  ONGOING: 'bg-ops-accent/10 text-ops-accent',
  COMPLETED: 'bg-ops-textDim/10 text-ops-textDim',
  CANCELLED: 'bg-ops-danger/10 text-ops-danger',
};

const REVIEW_BADGE: Record<RiskReviewStatus, string> = {
  DRAFT: 'bg-ops-textDim/10 text-ops-textDim',
  SUBMITTED: 'bg-ops-warning/10 text-ops-warning',
  APPROVED: 'bg-ops-success/10 text-ops-success',
  REJECTED: 'bg-ops-danger/10 text-ops-danger',
};

const LOG_ACTION_BADGE: Record<MissionApprovalLogEntry['action'], string> = {
  SUBMITTED: 'bg-ops-warning/10 text-ops-warning',
  APPROVED: 'bg-ops-success/10 text-ops-success',
  REJECTED: 'bg-ops-danger/10 text-ops-danger',
  REOPENED: 'bg-ops-accent/10 text-ops-accent',
};

export default function Missions() {
  const { can, user } = useAuth();
  const navigate = useNavigate();
  const [categoryFilter, setCategoryFilter] = useState('');
  const [approvalFilter, setApprovalFilter] = useState('');
  const [mineToApprove, setMineToApprove] = useState(false);
  const [awaitingMe, setAwaitingMe] = useState(0);
  const [units, setUnits] = useState<Unit[]>([]);
  const [personnel, setPersonnel] = useState<PersonnelListItem[]>([]);
  const [statusFilter, setStatusFilter] = useState('');
  const [reviewFilter, setReviewFilter] = useState('');
  const [logs, setLogs] = useState<MissionApprovalLogEntry[]>([]);
  const [missionNames, setMissionNames] = useState<Record<string, string>>({});
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    unitsApi.list().then((d) => setUnits(d.results.filter((u) => u.is_active))).catch(() => {});
    personnelApi.list({ page_size: 200 }).then((d) => setPersonnel(d.results)).catch(() => {});
  }, []);

  useEffect(() => {
    mrmApi.workQueue().then((q) => setAwaitingMe(q.missions_awaiting_my_approval ?? 0)).catch(() => {});
  }, [refresh]);

  useEffect(() => {
    missionsApi.approvalLogs({ page_size: 15, ordering: '-created_at' }).then((d) => setLogs(d.results)).catch(() => {});
  }, [refresh]);

  const fields = useMemo(() => buildMissionFields(units, personnel), [units, personnel]);

  const load = useCallback(
    (params: Record<string, string | number | boolean>) =>
      missionsApi.list({ ordering: '-created_at', ...params }).then((d) => {
        setMissionNames(Object.fromEntries(d.results.map((m) => [m.id, m.name])));
        return d.results;
      }),
    [],
  );

  const columns: ColumnDef<MissionListItem>[] = [
    { header: 'Mission', render: (m) => m.name, className: 'font-medium text-ops-text' },
    { header: 'Unit', render: (m) => m.unit_name ?? '—' },
    { header: 'Commander', render: (m) => m.commander_name ?? '—' },
    { header: 'Category', render: (m) => <span className="text-xs text-ops-textDim">{m.category_label}</span> },
    { header: 'Status', render: (m) => <span className={`${badgeClass} ${STATUS_BADGE[m.status]}`}>{m.status}</span> },
    {
      header: 'Approval',
      render: (m) => (m.category
        ? <span className={`${badgeClass} ${{ DRAFT: 'bg-ops-textDim/10 text-ops-textDim', PENDING: 'bg-ops-warning/10 text-ops-warning', APPROVED: 'bg-ops-success/10 text-ops-success', REJECTED: 'bg-ops-danger/10 text-ops-danger' }[m.approval_status]}`}>{m.approval_status}</span>
        : <span className="text-xs text-ops-textDim">—</span>),
    },
    {
      header: 'MRM prep.',
      render: (m) => (m.category ? <span className="text-xs text-ops-textDim">{m.mrm_preparation.label}</span> : <span className="text-xs text-ops-textDim">—</span>),
    },
    { header: 'Risk Review', render: (m) => <span className={`${badgeClass} ${REVIEW_BADGE[m.risk_review_status]}`}>{m.risk_review_status}</span> },
    { header: 'Overall Risk', render: (m) => <RiskLevelBadge level={m.overall_risk_level} /> },
    {
      header: 'MRM',
      render: (m) => (m.mrm
        ? <Link to={`/mrm/${m.mrm.id}`} className="flex items-center gap-2 hover:opacity-80"><StageBadge stage={m.mrm.stage as never} /><span className="font-mono text-xs text-ops-textDim">{m.mrm.total_percent.toFixed(0)}%</span></Link>
        : <span className="text-xs text-ops-textDim">—</span>),
    },
  ];

  const params: Record<string, string | number | boolean> = {};
  if (categoryFilter) params.category = categoryFilter;
  if (mineToApprove && user) { params.approval_status = 'PENDING'; params.approval_authority = user.id; }
  else if (approvalFilter) params.approval_status = approvalFilter;
  if (statusFilter) params.status = statusFilter;
  if (reviewFilter) params.risk_review_status = reviewFilter;

  return (
    <div className="space-y-6">
      <p className="text-sm text-ops-textDim">
        Mission profiles with hazard identification, probability/severity risk assessment, and approval workflow.
      </p>

      <ResourceManager<MissionListItem>
        noun="mission"
        addLabel="+ New Mission"
        columns={columns}
        fields={fields}
        load={load}
        create={missionsApi.create}
        update={missionsApi.update}
        remove={missionsApi.archive}
        fetchForEdit={(row) => missionsApi.get(row.id)}
        canCreate={false}
        canEdit={can('MISSIONS', 'EDIT')}
        canEditRow={(m) => !m.category}
        canDelete={can('MISSIONS', 'DELETE')}
        rowLabel={(m) => `Mission "${m.name}"`}
        searchPlaceholder="Search missions…"
        extraParams={params}
        onChanged={() => setRefresh((r) => r + 1)}
        formWidth="lg"
        toolbar={
          <>
            {can('MISSIONS', 'CREATE') && (
              <button onClick={() => navigate('/missions/new')} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg">+ New Mission</button>
            )}
            {awaitingMe > 0 && (
              <button onClick={() => setMineToApprove((v) => !v)}
                      className={`rounded-full border px-3 py-1 text-xs ${mineToApprove ? 'border-ops-warning bg-ops-warning/20 text-ops-warning' : 'border-ops-warning/40 bg-ops-warning/10 text-ops-warning'}`}>
                Awaiting my approval <span className="ml-1 font-mono font-bold">{awaitingMe}</span>
              </button>
            )}
            <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} className="rounded-md border border-ops-border bg-ops-panelLight px-2 py-1.5 text-xs text-ops-text">
              <option value="">All categories</option>
              <option value="GROUND_OPERATIONS">Ground Operations</option>
              <option value="AIR_OPERATIONS">Air Operations</option>
            </select>
            <select value={approvalFilter} onChange={(e) => { setApprovalFilter(e.target.value); setMineToApprove(false); }} className="rounded-md border border-ops-border bg-ops-panelLight px-2 py-1.5 text-xs text-ops-text">
              <option value="">Any approval</option>
              {['DRAFT', 'PENDING', 'APPROVED', 'REJECTED'].map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="rounded-md border border-ops-border bg-ops-panelLight px-2 py-1.5 text-xs text-ops-text">
              <option value="">All statuses</option>
              {['PLANNED', 'APPROVED', 'ONGOING', 'COMPLETED', 'CANCELLED'].map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <select value={reviewFilter} onChange={(e) => setReviewFilter(e.target.value)} className="rounded-md border border-ops-border bg-ops-panelLight px-2 py-1.5 text-xs text-ops-text">
              <option value="">All risk reviews</option>
              {['DRAFT', 'SUBMITTED', 'APPROVED', 'REJECTED'].map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </>
        }
        extraRowActions={(m) => (
          <>
            {m.category && ['DRAFT', 'REJECTED'].includes(m.approval_status) && can('MISSIONS', 'EDIT') && (
              <Link to={`/missions/${m.id}/edit`} className="text-xs font-medium text-ops-textDim hover:text-ops-text">Edit</Link>
            )}
            <Link to={`/missions/${m.id}`} className="text-xs font-medium text-ops-accent hover:underline">View →</Link>
          </>
        )}
      />

      <div className="ops-card overflow-hidden">
        <p className="border-b border-ops-border px-4 py-3 text-xs font-medium uppercase tracking-wider text-ops-textDim">
          Recent Approval Activity
        </p>
        <table className="w-full text-left text-sm">
          <thead className="bg-ops-panelLight text-xs uppercase tracking-wider text-ops-textDim">
            <tr>
              <th className="px-4 py-2">When</th>
              <th className="px-4 py-2">Mission</th>
              <th className="px-4 py-2">Action</th>
              <th className="px-4 py-2">By</th>
              <th className="px-4 py-2">Comments</th>
            </tr>
          </thead>
          <tbody>
            {logs.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-ops-textDim">No approval activity yet.</td></tr>
            )}
            {logs.map((l) => (
              <tr key={l.id} className="border-t border-ops-border">
                <td className="px-4 py-2 text-xs text-ops-textDim">{formatDateTime(l.created_at)}</td>
                <td className="px-4 py-2">
                  <Link to={`/missions/${l.mission}`} className="text-ops-text hover:text-ops-accent">{missionNames[l.mission] ?? 'Mission'}</Link>
                </td>
                <td className="px-4 py-2"><span className={`${badgeClass} ${LOG_ACTION_BADGE[l.action]}`}>{l.action}</span></td>
                <td className="px-4 py-2 text-xs">{l.actor_name ?? 'system'}</td>
                <td className="px-4 py-2 text-xs italic text-ops-textDim">{l.comments || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
