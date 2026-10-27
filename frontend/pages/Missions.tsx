import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { missionsApi, personnelApi, unitsApi } from '@/api/endpoints';
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
  const { can } = useAuth();
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
    { header: 'Status', render: (m) => <span className={`${badgeClass} ${STATUS_BADGE[m.status]}`}>{m.status}</span> },
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
        canCreate={can('MISSIONS', 'CREATE')}
        canEdit={can('MISSIONS', 'EDIT')}
        canDelete={can('MISSIONS', 'DELETE')}
        rowLabel={(m) => `Mission "${m.name}"`}
        searchPlaceholder="Search missions…"
        extraParams={params}
        onChanged={() => setRefresh((r) => r + 1)}
        formWidth="lg"
        toolbar={
          <>
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
          <Link to={`/missions/${m.id}`} className="text-xs font-medium text-ops-accent hover:underline">
            View →
          </Link>
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
