import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { mrmApi } from '@/api/mrmApi';
import { PercentBar, StageBadge } from '@/components/mrm/MrmBadges';
import { useMrmMe } from '@/components/mrm/useMrm';
import type { MrmListItem, WorkQueue } from '@/types/mrm';
import { extractApiError, formatDateTime } from '@/utils/errors';

const STAGES = [
  { value: '', label: 'All stages' },
  { value: 'draft', label: 'Drafts' },
  { value: 'awaiting_review', label: 'Awaiting review' },
  { value: 'needs_revision', label: 'Needs revision' },
  { value: 'awaiting_authority', label: 'Awaiting approval' },
  { value: 'approved', label: 'Approved' },
];

const ROLES = [
  { value: '', label: 'Any involvement' },
  { value: 'created', label: 'I created' },
  { value: 'review', label: 'I review' },
  { value: 'approve', label: 'I approve' },
  { value: 'tagged', label: 'I am tagged on' },
];

export default function MrmForms() {
  const me = useMrmMe();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [rows, setRows] = useState<MrmListItem[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [queue, setQueue] = useState<WorkQueue | null>(null);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [search, setSearch] = useState('');

  const stage = params.get('stage') ?? '';
  const role = params.get('role') ?? '';
  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    setParams(next, { replace: true });
    setPage(1);
  };

  useEffect(() => {
    mrmApi.workQueue().then(setQueue).catch(() => {});
  }, []);

  useEffect(() => {
    setIsLoading(true);
    const timer = setTimeout(() => {
      mrmApi.forms
        .list({ stage, role, search: search.trim(), page, page_size: 20 })
        .then((d) => { setRows(d.results); setCount(d.count); setError(''); })
        .catch((e) => setError(extractApiError(e, 'Unable to load MRM forms.')))
        .finally(() => setIsLoading(false));
    }, search ? 300 : 0);
    return () => clearTimeout(timer);
  }, [stage, role, search, page]);

  const chips: { label: string; count: number | undefined; stage?: string; role?: string }[] = queue ? [
    { label: 'Awaiting my review', count: queue.awaiting_my_review, stage: 'awaiting_review', role: 'review' },
    { label: 'Awaiting my approval', count: queue.awaiting_my_approval, stage: 'awaiting_authority', role: 'approve' },
    { label: 'Need my revision', count: queue.needs_revision, stage: 'needs_revision', role: 'created' },
    { label: 'My drafts', count: queue.my_drafts, stage: 'draft', role: 'created' },
    { label: 'Need an approver assigned', count: queue.needs_authority_assignment, stage: 'awaiting_authority' },
  ] : [];

  const selectClass = 'rounded-md border border-ops-border bg-ops-panelLight px-2 py-1.5 text-xs text-ops-text';
  const pages = Math.max(Math.ceil(count / 20), 1);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-ops-text">Mission Risk Management Forms</h1>
          <p className="text-sm text-ops-textDim">Hazard assessment, evaluator review and decision-authority approval for each mission or activity.</p>
        </div>
        {me?.can_author && (
          <button onClick={() => navigate('/mrm/new')} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg">
            + New MRM
          </button>
        )}
      </div>

      {chips.filter((c) => c.count).length > 0 && (
        <div className="flex flex-wrap gap-2">
          {chips.filter((c) => c.count).map((c) => (
            <button
              key={c.label}
              onClick={() => { const n = new URLSearchParams(); if (c.stage) n.set('stage', c.stage); if (c.role) n.set('role', c.role); setParams(n, { replace: true }); setPage(1); }}
              className="rounded-full border border-ops-warning/40 bg-ops-warning/10 px-3 py-1 text-xs text-ops-warning hover:bg-ops-warning/20"
            >
              {c.label} <span className="ml-1 font-mono font-bold">{c.count}</span>
            </button>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <input
          value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} placeholder="Search number, mission, creator…"
          className="w-64 rounded-md border border-ops-border bg-ops-panelLight px-3 py-1.5 text-xs text-ops-text outline-none focus:border-ops-accent"
        />
        <select value={stage} onChange={(e) => setFilter('stage', e.target.value)} className={selectClass}>
          {STAGES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        <select value={role} onChange={(e) => setFilter('role', e.target.value)} className={selectClass}>
          {ROLES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        <span className="ml-auto text-xs text-ops-textDim">{count} form(s)</span>
      </div>

      {error && <p className="text-sm text-ops-danger">{error}</p>}

      <div className="ops-card overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-ops-panelLight text-xs uppercase tracking-wider text-ops-textDim">
            <tr>
              <th className="px-4 py-3">MRM #</th>
              <th className="px-4 py-3">Activity / Mission</th>
              <th className="px-4 py-3">Unit</th>
              <th className="px-4 py-3">Stage</th>
              <th className="px-4 py-3">Residual risk</th>
              <th className="px-4 py-3">Decision authority</th>
              <th className="px-4 py-3">Created</th>
            </tr>
          </thead>
          <tbody>
            {!isLoading && rows.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-ops-textDim">No MRM forms match these filters.</td></tr>
            )}
            {rows.map((f) => (
              <tr key={f.id} onClick={() => navigate(`/mrm/${f.id}`)} className="cursor-pointer border-t border-ops-border hover:bg-ops-panelLight/50">
                <td className="px-4 py-3 font-mono text-xs text-ops-accent">{f.mrm_number}</td>
                <td className="px-4 py-3">
                  <p className="font-medium text-ops-text">{f.activity_mission}</p>
                  {f.mission_name && (
                    <Link to={`/missions/${f.mission}`} onClick={(e) => e.stopPropagation()} className="text-xs text-ops-textDim hover:text-ops-accent">
                      ⚑ {f.mission_name}
                    </Link>
                  )}
                </td>
                <td className="px-4 py-3 text-xs">{f.unit_code}</td>
                <td className="px-4 py-3"><StageBadge stage={f.stage} /></td>
                <td className="px-4 py-3"><PercentBar percent={f.total_percent} /></td>
                <td className="px-4 py-3 text-xs">
                  <p className="text-ops-text">{f.authority_level_label}</p>
                  <p className="text-ops-textDim">{f.authority_name || (f.stage === 'needs_authority_assignment' ? 'Unassigned' : '—')}</p>
                </td>
                <td className="px-4 py-3 text-xs text-ops-textDim">{formatDateTime(f.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pages > 1 && (
        <div className="flex items-center justify-end gap-3 text-xs text-ops-textDim">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="rounded-md border border-ops-border px-3 py-1 disabled:opacity-40">Previous</button>
          Page {page} of {pages}
          <button disabled={page >= pages} onClick={() => setPage(page + 1)} className="rounded-md border border-ops-border px-3 py-1 disabled:opacity-40">Next</button>
        </div>
      )}
    </div>
  );
}
