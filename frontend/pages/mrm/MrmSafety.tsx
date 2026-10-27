import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';

import { unitsApi } from '@/api/endpoints';
import { mrmApi } from '@/api/mrmApi';
import { SearchField, TextField, badgeClass } from '@/components/common/FormFields';
import Modal from '@/components/common/Modal';
import type { FieldDef } from '@/components/common/RecordForm';
import ResourceManager, { ColumnDef } from '@/components/common/ResourceManager';
import { AUTHORITY_LABEL } from '@/components/mrm/MrmBadges';
import { useMrmMe } from '@/components/mrm/useMrm';
import { useToast } from '@/contexts/ToastContext';
import type { Unit } from '@/types';
import type { MrmAnalytics, SafetyAssignment, SafetyUser, UnitLogoItem } from '@/types/mrm';
import { extractApiError, formatDateTime } from '@/utils/errors';

type Tab = 'analytics' | 'users' | 'assignments' | 'logos';

export default function MrmSafety() {
  const me = useMrmMe();
  const [tab, setTab] = useState<Tab>('analytics');
  if (!me) return <p className="text-sm text-ops-textDim">Loading…</p>;
  if (!me.is_admin && !me.is_safety_officer) {
    return <div className="ops-card p-6 text-sm text-ops-textDim">The Safety Office is for Unit Safety Officers and Administrators.</div>;
  }
  const tabs: [Tab, string][] = [['analytics', 'Analytics'], ['users', 'Unit users'], ['logos', 'Unit logos'], ...(me.is_admin ? [['assignments', 'Officer assignments'] as [Tab, string]] : [])];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-ops-text">Safety Office</h1>
        <p className="text-sm text-ops-textDim">Oversight for {me.is_admin ? 'all units' : 'the units you are assigned to'}.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {tabs.map(([key, label]) => (
          <button key={key} onClick={() => setTab(key)}
                  className={`rounded-md border px-3 py-1.5 text-xs font-medium ${tab === key ? 'border-ops-accent bg-ops-accent/10 text-ops-accent' : 'border-ops-border text-ops-textDim hover:text-ops-text'}`}>{label}</button>
        ))}
      </div>
      {tab === 'analytics' && <Analytics />}
      {tab === 'users' && <UsersTab />}
      {tab === 'logos' && <LogosTab />}
      {tab === 'assignments' && <AssignmentsTab />}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return <div className="ops-card p-4"><p className="text-[10px] uppercase tracking-wider text-ops-textDim">{label}</p><p className="text-2xl font-semibold text-ops-text">{value}</p></div>;
}

function BarList({ title, data }: { title: string; data: Record<string, number> }) {
  const max = Math.max(...Object.values(data), 1);
  return (
    <div className="ops-card space-y-2 p-4">
      <p className="ops-label">{title}</p>
      {Object.keys(data).length === 0 && <p className="text-xs text-ops-textDim">No data.</p>}
      {Object.entries(data).map(([k, v]) => (
        <div key={k} className="flex items-center gap-2 text-xs">
          <span className="w-40 truncate text-ops-textDim">{k.replace(/_/g, ' ')}</span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-ops-panelLight"><div className="h-full bg-ops-accent" style={{ width: `${(v / max) * 100}%` }} /></div>
          <span className="w-8 text-right font-mono text-ops-text">{v}</span>
        </div>
      ))}
    </div>
  );
}

function Analytics() {
  const [data, setData] = useState<MrmAnalytics | null>(null);
  const [range, setRange] = useState({ from: '', to: '' });
  const [error, setError] = useState('');
  useEffect(() => { mrmApi.safety.analytics(range).then(setData).catch((e) => setError(extractApiError(e))); }, [range]);
  if (error) return <p className="text-sm text-ops-danger">{error}</p>;
  if (!data) return <p className="text-sm text-ops-textDim">Loading…</p>;
  const r = data.feedback.avg_ratings;
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 text-xs text-ops-textDim">
        From <input type="date" value={range.from} onChange={(e) => setRange({ ...range, from: e.target.value })} className="rounded-md border border-ops-border bg-ops-panelLight px-2 py-1 text-ops-text" />
        to <input type="date" value={range.to} onChange={(e) => setRange({ ...range, to: e.target.value })} className="rounded-md border border-ops-border bg-ops-panelLight px-2 py-1 text-ops-text" />
      </div>
      <div className="grid gap-3 md:grid-cols-4">
        <Stat label="MRM forms" value={data.totals.forms} /><Stat label="Approved" value={data.totals.approved} />
        <Stat label="Avg. time to approval" value={`${data.avg_completion_hours} h`} /><Stat label="Feedback pending review" value={data.feedback.pending} />
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <BarList title="By stage" data={data.totals.stages} />
        <BarList title="Risk category" data={data.risk_category} />
        <BarList title="Decision tier required" data={data.authority_level} />
        <BarList title="Forms per month" data={data.by_month} />
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="ops-card p-4">
          <p className="ops-label mb-2">Most-used hazards</p>
          {data.top_hazards.length === 0 && <p className="text-xs text-ops-textDim">None yet.</p>}
          {data.top_hazards.map((h, i) => (
            <div key={i} className="flex justify-between gap-3 border-b border-ops-border py-1.5 text-xs last:border-0">
              <span className="text-ops-text">{h.hazard_description}</span><span className="font-mono text-ops-textDim">{h.uses}×</span>
            </div>
          ))}
        </div>
        <div className="ops-card space-y-1 p-4 text-sm">
          <p className="ops-label mb-2">Feedback quality (avg of 5)</p>
          <p className="text-ops-text">Risk assessment accuracy: <b>{r.accuracy ?? '—'}</b></p>
          <p className="text-ops-text">Hazard identification: <b>{r.identification ?? '—'}</b></p>
          <p className="text-ops-text">Mitigation effectiveness: <b>{r.mitigation ?? '—'}</b></p>
          <p className="pt-2 text-xs text-ops-textDim">{data.feedback.total} responses · {data.feedback.reviewed} reviewed · {data.feedback.action_taken} actioned</p>
        </div>
      </div>
    </div>
  );
}

function UsersTab() {
  const { showSuccess, showError } = useToast();
  const [rows, setRows] = useState<SafetyUser[]>([]);
  const [search, setSearch] = useState('');
  const [resetFor, setResetFor] = useState<SafetyUser | null>(null);

  const load = useCallback(() => {
    mrmApi.safety.users({ search: search.trim(), page_size: 100 }).then((d) => setRows(d.results)).catch((e) => showError(extractApiError(e)));
  }, [search, showError]);
  useEffect(() => { const t = setTimeout(load, search ? 300 : 0); return () => clearTimeout(t); }, [load, search]);

  const toggle = async (u: SafetyUser) => {
    try { await mrmApi.safety.toggleActive(u.id); showSuccess(`${u.username} ${u.is_active ? 'deactivated' : 'activated'}.`); load(); } catch (e) { showError(extractApiError(e)); }
  };

  return (
    <div className="space-y-3">
      <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search users in your units…"
             className="w-72 rounded-md border border-ops-border bg-ops-panelLight px-3 py-1.5 text-xs text-ops-text outline-none focus:border-ops-accent" />
      <div className="ops-card overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-ops-panelLight text-xs uppercase tracking-wider text-ops-textDim">
            <tr><th className="px-4 py-3">User</th><th className="px-4 py-3">Unit</th><th className="px-4 py-3">MRM authority</th><th className="px-4 py-3">Signature</th><th className="px-4 py-3">Last login</th><th className="px-4 py-3" /></tr>
          </thead>
          <tbody>
            {rows.map((u) => (
              <tr key={u.id} className={`border-t border-ops-border ${u.is_active ? '' : 'opacity-50'}`}>
                <td className="px-4 py-3"><p className="text-ops-text">{u.full_name}</p><p className="font-mono text-xs text-ops-textDim">{u.username}</p></td>
                <td className="px-4 py-3 text-xs">{u.unit ?? '—'}</td>
                <td className="px-4 py-3 text-xs">{AUTHORITY_LABEL[u.mrm_authority] ?? '—'}{u.mrm_designation && <span className="text-ops-textDim"> · {u.mrm_designation.replace(/_/g, ' ').toLowerCase()}</span>}</td>
                <td className="px-4 py-3 text-xs">{u.has_signature ? '✓' : <span className="text-ops-warning">missing</span>}</td>
                <td className="px-4 py-3 text-xs text-ops-textDim">{formatDateTime(u.last_login)}</td>
                <td className="whitespace-nowrap px-4 py-3 text-right text-xs">
                  <button onClick={() => setResetFor(u)} className="mr-3 text-ops-textDim hover:text-ops-text">Reset password</button>
                  <button onClick={() => toggle(u)} className={u.is_active ? 'text-ops-danger hover:underline' : 'text-ops-success hover:underline'}>{u.is_active ? 'Deactivate' : 'Activate'}</button>
                </td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={6} className="px-4 py-6 text-center text-ops-textDim">No users in your units.</td></tr>}
          </tbody>
        </table>
      </div>
      {resetFor && <ResetPasswordModal user={resetFor} onClose={() => setResetFor(null)} />}
    </div>
  );
}

function ResetPasswordModal({ user, onClose }: { user: SafetyUser; onClose: () => void }) {
  const { showSuccess } = useToast();
  const [pw, setPw] = useState({ a: '', b: '' });
  const [error, setError] = useState('');
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try { await mrmApi.safety.resetPassword(user.id, pw.a, pw.b); showSuccess(`Password reset for ${user.username}.`); onClose(); } catch (err) { setError(extractApiError(err)); }
  };
  return (
    <Modal title={`Reset password — ${user.username}`} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <p className="text-xs text-ops-textDim">The user will be required to choose their own password at next login.</p>
        <TextField label="New password" type="password" required value={pw.a} onChange={(v) => setPw({ ...pw, a: v })} />
        <TextField label="Confirm password" type="password" required value={pw.b} onChange={(v) => setPw({ ...pw, b: v })} />
        {error && <p className="text-xs text-ops-danger">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-textDim">Cancel</button>
          <button className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg">Reset</button>
        </div>
      </form>
    </Modal>
  );
}

function LogosTab() {
  const { showSuccess, showError } = useToast();
  const [units, setUnits] = useState<Unit[]>([]);
  const [logos, setLogos] = useState<UnitLogoItem[]>([]);
  const [unit, setUnit] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);

  const load = useCallback(() => { mrmApi.logos.list().then(setLogos).catch(() => {}); }, []);
  useEffect(() => { unitsApi.list().then((d) => setUnits(d.results.filter((u) => u.is_active))).catch(() => {}); load(); }, [load]);

  const upload = async (e: FormEvent) => {
    e.preventDefault();
    if (!unit || !file) return;
    try { await mrmApi.logos.upload(unit, file); showSuccess('Logo saved.'); setFile(null); load(); } catch (err) { showError(extractApiError(err)); }
  };

  return (
    <div className="space-y-4">
      <form onSubmit={upload} className="ops-card grid gap-3 p-4 md:grid-cols-[1fr_1fr_auto] md:items-end">
        <SearchField label="Unit" value={unit} onChange={setUnit} options={units.map((u) => ({ value: u.id, label: u.name, sublabel: u.code }))} />
        <div>
          <label className="mb-1 block text-xs text-ops-textDim">Logo (PNG/JPEG, ≤2 MB)</label>
          <input type="file" accept="image/png,image/jpeg" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="block w-full text-xs text-ops-textDim file:mr-3 file:rounded-md file:border file:border-ops-border file:bg-ops-panelLight file:px-3 file:py-1.5 file:text-xs file:text-ops-text" />
        </div>
        <button disabled={!unit || !file} className="rounded-md bg-ops-accent px-3 py-2 text-xs font-semibold text-ops-bg disabled:opacity-50">Upload</button>
      </form>
      <div className="ops-card">
        {logos.length === 0 && <p className="p-5 text-sm text-ops-textDim">No unit logos yet — PDFs use the default PAF crest.</p>}
        {logos.map((l) => (
          <div key={l.id} className="flex items-center justify-between border-b border-ops-border px-5 py-3 last:border-0 text-sm">
            <span className="text-ops-text">{l.unit_name} <span className="font-mono text-xs text-ops-textDim">{l.unit_code}</span></span>
            <button onClick={async () => { try { await mrmApi.logos.remove(l.id); load(); } catch (e) { showError(extractApiError(e)); } }} className="text-xs text-ops-danger hover:underline">Remove</button>
          </div>
        ))}
      </div>
    </div>
  );
}

function AssignmentsTab() {
  const [units, setUnits] = useState<Unit[]>([]);
  const [officers, setOfficers] = useState<SafetyUser[]>([]);
  useEffect(() => {
    unitsApi.list().then((d) => setUnits(d.results.filter((u) => u.is_active))).catch(() => {});
    mrmApi.safety.users({ authority: 'UNIT_SAFETY_OFFICER', page_size: 200 }).then((d) => setOfficers(d.results)).catch(() => {});
  }, []);

  const fields: FieldDef[] = useMemo(() => [
    { name: 'user', label: 'Unit Safety Officer', type: 'search', required: true, span: 2, options: officers.map((o) => ({ value: o.id, label: o.full_name, sublabel: o.username })) },
    { name: 'unit', label: 'Unit (and its sub-units)', type: 'search', required: true, span: 2, options: units.map((u) => ({ value: u.id, label: u.name, sublabel: u.code })) },
    { name: 'is_primary', label: 'Primary unit', type: 'checkbox' },
  ], [officers, units]);

  const columns: ColumnDef<SafetyAssignment>[] = [
    { header: 'Officer', render: (a) => <>{a.user_name} <span className="font-mono text-xs text-ops-textDim">{a.username}</span></> },
    { header: 'Unit', render: (a) => `${a.unit_name} (${a.unit_code})` },
    { header: 'Primary', render: (a) => (a.is_primary ? <span className={`${badgeClass} bg-ops-accent/10 text-ops-accent`}>primary</span> : '—') },
  ];
  const load = useCallback(() => mrmApi.safety.assignments().then((d) => d.results), []);

  return (
    <ResourceManager<SafetyAssignment>
      noun="assignment" addLabel="+ Assign unit" columns={columns} fields={fields} load={load}
      create={mrmApi.safety.createAssignment as (p: unknown) => Promise<unknown>} remove={mrmApi.safety.removeAssignment}
      removeVerb="Delete" supportsArchive={false} canCreate canDelete rowLabel={(a) => `${a.username} → ${a.unit_code}`}
      emptyText="No assignments. A Safety Officer oversees their home unit and its sub-units by default."
    />
  );
}
