import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { mrmApi } from '@/api/mrmApi';
import { badgeClass } from '@/components/common/FormFields';
import RecordFormModal, { FieldDef } from '@/components/common/RecordForm';
import { useMrmConfig, useMrmMe } from '@/components/mrm/useMrm';
import { useToast } from '@/contexts/ToastContext';
import type { MrmFeedbackItem, MrmListItem } from '@/types/mrm';
import { extractApiError, formatDateTime } from '@/utils/errors';

const STATUS_BADGE: Record<MrmFeedbackItem['status'], string> = {
  pending: 'bg-ops-warning/10 text-ops-warning',
  reviewed: 'bg-ops-accent/10 text-ops-accent',
  action_taken: 'bg-ops-success/10 text-ops-success',
};

export default function MrmFeedback() {
  const me = useMrmMe();
  const [tab, setTab] = useState<'mine' | 'inbox'>('mine');
  const canReview = !!me && (me.is_admin || me.is_safety_officer || me.authority === 'EVALUATOR');

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-ops-text">Post-Mission Feedback</h1>
        <p className="text-sm text-ops-textDim">Crew feedback feeds lessons learned and hazard-registry improvements.</p>
      </div>
      <div className="flex gap-2">
        {([['mine', 'My feedback'], ...(canReview ? [['inbox', 'Review inbox']] : [])] as [string, string][]).map(([key, label]) => (
          <button key={key} onClick={() => setTab(key as 'mine' | 'inbox')}
                  className={`rounded-md border px-3 py-1.5 text-xs font-medium ${tab === key ? 'border-ops-accent bg-ops-accent/10 text-ops-accent' : 'border-ops-border text-ops-textDim hover:text-ops-text'}`}>{label}</button>
        ))}
      </div>
      {tab === 'mine' ? <MyFeedback /> : <Inbox />}
    </div>
  );
}

function MyFeedback() {
  const [data, setData] = useState<{ stats: { total_tagged: number; pending_feedback: number; completed_feedback: number }; pending: MrmListItem[]; completed: MrmFeedbackItem[] } | null>(null);
  useEffect(() => { mrmApi.feedback.mine().then(setData).catch(() => {}); }, []);
  if (!data) return <p className="text-sm text-ops-textDim">Loading…</p>;

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-3">
        {[['Missions I was on', data.stats.total_tagged], ['Awaiting my feedback', data.stats.pending_feedback], ['Feedback given', data.stats.completed_feedback]].map(([label, n]) => (
          <div key={label as string} className="ops-card p-4"><p className="text-[10px] uppercase tracking-wider text-ops-textDim">{label}</p><p className="text-2xl font-semibold text-ops-text">{n}</p></div>
        ))}
      </div>
      <div className="ops-card">
        <p className="ops-label border-b border-ops-border px-5 py-3">Waiting for your feedback</p>
        {data.pending.length === 0 && <p className="p-5 text-sm text-ops-textDim">You are all caught up.</p>}
        {data.pending.map((f) => (
          <Link key={f.id} to={`/mrm/${f.id}`} className="flex items-center justify-between border-b border-ops-border px-5 py-3 last:border-0 hover:bg-ops-panelLight/50">
            <div><p className="text-sm text-ops-text">{f.activity_mission}</p><p className="text-xs text-ops-textDim">MRM {f.mrm_number} · approved {formatDateTime(f.authority_approval_date)}</p></div>
            <span className="text-xs text-ops-accent">Give feedback →</span>
          </Link>
        ))}
      </div>
      <div className="ops-card">
        <p className="ops-label border-b border-ops-border px-5 py-3">Feedback I have given</p>
        {data.completed.length === 0 && <p className="p-5 text-sm text-ops-textDim">Nothing yet.</p>}
        {data.completed.map((fb) => (
          <div key={fb.id} className="flex items-center justify-between border-b border-ops-border px-5 py-3 last:border-0 text-sm">
            <div><p className="text-ops-text">{fb.activity_mission}</p><p className="text-xs text-ops-textDim">MRM {fb.mrm_number} · {formatDateTime(fb.submitted_at)}</p></div>
            <span className={`${badgeClass} ${STATUS_BADGE[fb.status]}`}>{fb.status.replace('_', ' ')}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Inbox() {
  const config = useMrmConfig();
  const { showSuccess } = useToast();
  const [status, setStatus] = useState('pending');
  const [rows, setRows] = useState<MrmFeedbackItem[]>([]);
  const [error, setError] = useState('');
  const [open, setOpen] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState<MrmFeedbackItem | null>(null);

  const load = useCallback(() => {
    mrmApi.feedback.list({ status, page_size: 50 }).then((d) => setRows(d.results)).catch((e) => setError(extractApiError(e)));
  }, [status]);
  useEffect(load, [load]);

  const L = Object.entries(config?.likelihoods ?? {}).sort((a, b) => Number(b[0]) - Number(a[0])).map(([k, v]) => ({ value: k, label: `${k} — ${v}` }));
  const S = Object.entries(config?.severities ?? {}).map(([k, v]) => ({ value: k, label: `${k} — ${v}` }));

  const fields: FieldDef[] = [
    { name: 'action', label: 'Decision', type: 'select', required: true, defaultValue: 'review', span: 2,
      options: [{ value: 'review', label: 'Mark as reviewed' }, { value: 'take_action', label: 'Action taken' }, { value: 'dismiss', label: 'Dismiss — no action needed' }] },
    { name: 'review_notes', label: 'Review notes', type: 'textarea' },
    { name: 'action_taken', label: 'Action taken (required for “Action taken”)', type: 'textarea' },
    { name: 'add_hazard', label: 'Add a new hazard to the registry from this feedback', type: 'checkbox', help: 'Only with “Action taken”.' },
    { name: 'nh_description', label: 'Hazard description', type: 'textarea', defaultValue: reviewing?.recommended_hazard_description ?? '' },
    { name: 'nh_activity', label: 'Activity code', type: 'text', defaultValue: reviewing?.activity_mission ?? '' },
    { name: 'nh_mitigations', label: 'Mitigations', type: 'textarea', defaultValue: reviewing?.recommended_mitigations ?? '' },
    { name: 'nh_bl', label: 'Likelihood before', type: 'select', options: L }, { name: 'nh_bs', label: 'Severity before', type: 'select', options: S },
    { name: 'nh_al', label: 'Likelihood after', type: 'select', options: L }, { name: 'nh_as', label: 'Severity after', type: 'select', options: S },
  ];

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="rounded-md border border-ops-border bg-ops-panelLight px-2 py-1.5 text-xs text-ops-text">
          <option value="pending">Pending</option><option value="reviewed">Reviewed</option><option value="action_taken">Action taken</option><option value="">All</option>
        </select>
        <span className="text-xs text-ops-textDim">{rows.length} item(s)</span>
      </div>
      {error && <p className="text-sm text-ops-danger">{error}</p>}
      {rows.length === 0 && <div className="ops-card p-6 text-center text-sm text-ops-textDim">Nothing in this view.</div>}
      {rows.map((fb) => (
        <div key={fb.id} className="ops-card p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <button onClick={() => setOpen(open === fb.id ? null : fb.id)} className="text-left">
              <p className="text-sm font-medium text-ops-text">{fb.activity_mission} <span className="font-mono text-xs text-ops-accent">#{fb.mrm_number}</span></p>
              <p className="text-xs text-ops-textDim">{fb.submitted_by ?? 'Anonymous'} · {fb.unit_name} · {formatDateTime(fb.submitted_at)}</p>
            </button>
            <div className="flex items-center gap-3">
              {fb.recommend_add_to_hazard_registry && <span className={`${badgeClass} bg-ops-accent/10 text-ops-accent`}>hazard suggested</span>}
              <span className={`${badgeClass} ${STATUS_BADGE[fb.status]}`}>{fb.status.replace('_', ' ')}</span>
              {fb.can_review && fb.status !== 'action_taken' && <button onClick={() => setReviewing(fb)} className="rounded-md bg-ops-accent px-3 py-1 text-xs font-semibold text-ops-bg">Review</button>}
            </div>
          </div>
          {open === fb.id && (
            <div className="mt-3 space-y-1 border-t border-ops-border pt-3 text-sm text-ops-text">
              <p className="font-mono text-xs text-ops-textDim">Accuracy {fb.risk_assessment_accuracy}/5 · Hazards {fb.hazard_identification_rating}/5 · Mitigations {fb.mitigation_effectiveness}/5</p>
              {([['Went well', fb.what_went_well], ['Could improve', fb.what_could_be_improved], ['New hazards', fb.new_hazards_identified], ['Lessons', fb.lessons_learned],
                 ['Comments', fb.additional_comments], ['Recommended hazard', fb.recommended_hazard_description], ['Recommended mitigations', fb.recommended_mitigations],
                 ['Review notes', fb.review_notes], ['Action taken', fb.action_taken]] as [string, string][]).filter(([, v]) => v).map(([k, v]) => <p key={k}><b>{k}:</b> {v}</p>)}
              <Link to={`/mrm/${fb.mrm}`} className="inline-block pt-1 text-xs text-ops-accent hover:underline">Open MRM →</Link>
            </div>
          )}
        </div>
      ))}

      {reviewing && (
        <RecordFormModal
          key={reviewing.id} title={`Review feedback — MRM ${reviewing.mrm_number}`} width="lg" fields={fields}
          transformPayload={(p) => {
            const { add_hazard, nh_description, nh_activity, nh_mitigations, nh_bl, nh_bs, nh_al, nh_as, ...rest } = p;
            return {
              ...rest,
              ...(add_hazard && rest.action === 'take_action' ? { new_hazard: {
                hazard_description: nh_description, activity_code: nh_activity, mitigations: nh_mitigations,
                before_likelihood: nh_bl, before_severity: nh_bs, after_likelihood: nh_al, after_severity: nh_as } } : {}),
            };
          }}
          onSubmit={async (body) => { await mrmApi.feedback.review(reviewing.id, body); showSuccess('Feedback updated.'); setReviewing(null); load(); }}
          onClose={() => setReviewing(null)}
        />
      )}
    </div>
  );
}

