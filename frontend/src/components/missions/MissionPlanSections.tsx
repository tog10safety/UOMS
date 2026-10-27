import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { missionOpsApi } from '@/api/missionOps';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import { TextAreaField } from '@/components/common/FormFields';
import Modal from '@/components/common/Modal';
import { useToast } from '@/contexts/ToastContext';
import type { ActivityEvent, ApprovalStatus, MissionPlan, MrmPrepStatus } from '@/types/missionOps';
import { extractApiError, formatDateTime } from '@/utils/errors';

const APPROVAL_BADGE: Record<ApprovalStatus, string> = {
  DRAFT: 'bg-ops-textDim/10 text-ops-textDim', PENDING: 'bg-ops-warning/10 text-ops-warning',
  APPROVED: 'bg-ops-success/10 text-ops-success', REJECTED: 'bg-ops-danger/10 text-ops-danger',
};
const MRM_BADGE: Record<MrmPrepStatus, string> = {
  NOT_STARTED: 'bg-ops-textDim/10 text-ops-textDim', IN_PROGRESS: 'bg-ops-accent/10 text-ops-accent',
  REVISION_REQUIRED: 'bg-orange-500/10 text-orange-400', SUBMITTED: 'bg-ops-warning/10 text-ops-warning', APPROVED: 'bg-ops-success/10 text-ops-success',
};

function Card({ n, title, children, right }: { n: number; title: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <section className="ops-card space-y-3 p-5">
      <div className="flex items-center justify-between gap-3">
        <p className="ops-label">{n} · {title}</p>
        {right}
      </div>
      {children}
    </section>
  );
}
const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div><p className="text-[10px] uppercase tracking-wider text-ops-textDim">{label}</p><div className="text-sm text-ops-text">{children || '—'}</div></div>
);

export default function MissionPlanSections({ plan, onReload }: { plan: MissionPlan; onReload: () => void }) {
  const { showSuccess, showError } = useToast();
  const [activity, setActivity] = useState<ActivityEvent[] | null>(null);
  const [decision, setDecision] = useState<'approve' | 'reject' | null>(null);
  const [comments, setComments] = useState('');
  const [decisionError, setDecisionError] = useState('');
  const [confirmSubmit, setConfirmSubmit] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => { missionOpsApi.activity(plan.id).then(setActivity).catch(() => setActivity([])); }, [plan.id, plan.approval.status, plan.mrm_preparation.status, plan.updated_at]);

  const decide = async () => {
    if (!decision || busy) return;
    if (decision === 'reject' && !comments.trim()) { setDecisionError('Give a reason for rejecting the mission.'); return; }
    setBusy(true);
    try {
      if (decision === 'approve') await missionOpsApi.approve(plan.id, comments);
      else await missionOpsApi.reject(plan.id, comments);
      showSuccess(decision === 'approve' ? 'Mission approved. The creator has been notified.' : 'Mission rejected. The creator has been notified.');
      setDecision(null); setComments(''); setDecisionError('');
      onReload();
    } catch (e) { setDecisionError(extractApiError(e)); } finally { setBusy(false); }
  };

  const submit = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const res = await missionOpsApi.submit(plan.id);
      showSuccess(res.newly_submitted === false ? 'Already submitted.' : 'Submitted. The authority and the MRM assignee have been notified.');
      setConfirmSubmit(false);
      onReload();
    } catch (e) { showError(extractApiError(e)); setConfirmSubmit(false); } finally { setBusy(false); }
  };

  const a = plan.approval;
  const mrm = plan.mrm_preparation;

  return (
    <div className="space-y-5">
      <Card n={1} title="Mission information" right={plan.can.edit ? <Link to={`/missions/${plan.id}/edit`} className="text-xs text-ops-accent hover:underline">Edit mission</Link> : undefined}>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Mission / Activity">{plan.name}</Field>
          <Field label="Operational status">{plan.status}</Field>
          <Field label="Estimated start">{formatDateTime(plan.start_date)}</Field>
          <Field label="Estimated end">{formatDateTime(plan.end_date)}</Field>
          <div className="md:col-span-2"><Field label="Details">{plan.description}</Field></div>
          <Field label="Created by">{plan.created_by_name}</Field>
        </div>
      </Card>

      <Card n={2} title="Mission category">
        <span className="rounded-full bg-ops-accent/10 px-3 py-1 text-xs font-semibold text-ops-accent">{plan.category_label}</span>
      </Card>

      <Card n={3} title="Unit and office/section responsibility">
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Unit Primary Responsible (UPR)">{plan.unit_name}{plan.unit_code ? ` (${plan.unit_code})` : ''}</Field>
          <Field label="Office/Section Primary Responsible (O/SPR)">{plan.responsible_section_name}</Field>
        </div>
      </Card>

      <Card n={4} title={`Personnel and assigned roles (${plan.personnel.length})`}>
        {plan.personnel.length === 0 ? <p className="text-sm text-ops-textDim">No personnel assigned.</p> : (
          <div className="overflow-hidden rounded-md border border-ops-border">
            <table className="w-full text-left text-sm">
              <thead className="bg-ops-panelLight text-xs uppercase tracking-wider text-ops-textDim"><tr><th className="px-3 py-2">Person</th><th className="px-3 py-2">Service #</th><th className="px-3 py-2">Unit</th><th className="px-3 py-2">Role</th></tr></thead>
              <tbody>
                {plan.personnel.map((p) => (
                  <tr key={p.id} className="border-t border-ops-border">
                    <td className="px-3 py-2 text-ops-text">{p.person.rank} {p.person.name}</td>
                    <td className="px-3 py-2 font-mono text-xs text-ops-textDim">{p.person.service_number}</td>
                    <td className="px-3 py-2 text-xs">{p.person.unit ?? '—'}</td>
                    <td className="px-3 py-2">{p.role_label}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card n={5} title={`Vehicle assignments (${plan.vehicles.length})`}>
        {plan.vehicles.length === 0 ? <p className="text-sm text-ops-textDim">No vehicles assigned — this mission needs no transport.</p> : plan.vehicles.map((v) => (
          <div key={v.id} className="rounded-md border border-ops-border p-3 text-sm">
            <p className="font-medium text-ops-text">
              {v.is_pov ? v.pov?.plate_number : v.fleet?.plate_number}{' '}
              <span className="text-ops-textDim">— {[v.is_pov ? v.pov?.vehicle_type : v.fleet?.vehicle_type, v.is_pov ? v.pov?.make : v.fleet?.make, v.is_pov ? v.pov?.model : v.fleet?.model].filter(Boolean).join(' · ')}</span>{' '}
              {v.is_pov && <span className="rounded-full bg-ops-warning/10 px-2 py-0.5 text-[10px] font-semibold uppercase text-ops-warning">Privately owned</span>}
            </p>
            <p className="text-xs text-ops-textDim">Driver: {v.driver_name ?? '—'}{v.is_pov && v.pov?.owner_name ? ` · Owner: ${v.pov.owner_name}` : ''}{v.notes ? ` · ${v.notes}` : ''}</p>
            {v.is_pov && <p className="text-[11px] text-ops-textDim">Not part of the fleet — no odometer is tracked.</p>}
          </div>
        ))}
      </Card>

      <Card n={6} title="Vehicle itineraries">
        {plan.vehicles.every((v) => v.itinerary.length === 0) ? <p className="text-sm text-ops-textDim">No itineraries recorded.</p> : plan.vehicles.filter((v) => v.itinerary.length).map((v) => (
          <div key={v.id} className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-ops-textDim">{v.is_pov ? `POV ${v.pov?.plate_number}` : v.fleet?.plate_number}</p>
            {v.itinerary.map((leg) => (
              <ol key={leg.id} className="space-y-1 rounded-md border border-ops-border p-3 text-sm">
                <li className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-xs font-semibold text-ops-accent">Leg {leg.sequence}</span>
                  <span className="text-xs text-ops-textDim">{leg.planned_departure ? `Dep ${formatDateTime(leg.planned_departure)}` : ''}{leg.planned_arrival ? ` · Arr ${formatDateTime(leg.planned_arrival)}` : ''}</span>
                </li>
                {[{ tag: 'Origin', p: leg.origin }, ...leg.stops.map((s, i) => ({ tag: `Stop ${i + 1}`, p: s })), { tag: 'Destination', p: leg.destination }].map(({ tag, p }, i) => (
                  <li key={i} className="flex flex-wrap items-baseline gap-x-3 pl-2">
                    <span className="w-20 text-[10px] uppercase tracking-wider text-ops-textDim">{tag}</span>
                    <span className="text-ops-text">{p.name}</span>
                    <span className="font-mono text-xs text-ops-accent">{p.mgrs}</span>
                    <span className="font-mono text-[11px] text-ops-textDim">{p.lat.toFixed(5)}, {p.lng.toFixed(5)}</span>
                  </li>
                ))}
                {leg.notes && <li className="pl-2 text-xs italic text-ops-textDim">{leg.notes}</li>}
              </ol>
            ))}
          </div>
        ))}
      </Card>

      <Card n={7} title="Authority and approval status">
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="Approving authority">{a.authority ? `${a.authority.name}${a.authority.unit ? ` (${a.authority.unit})` : ''}` : null}</Field>
          <Field label="Status"><span className={`rounded-full px-2 py-0.5 text-xs font-medium ${APPROVAL_BADGE[a.status]}`}>{a.status_label}</span></Field>
          <Field label="Submitted">{a.submitted_at ? formatDateTime(a.submitted_at) : null}</Field>
          {a.decided_at && <Field label="Decision by">{`${a.decided_by_name ?? '—'} · ${formatDateTime(a.decided_at)}`}</Field>}
          {a.comments && <div className="md:col-span-2"><Field label={a.status === 'REJECTED' ? 'Reason for rejection' : 'Comments'}>{a.comments}</Field></div>}
        </div>
        <div className="flex flex-wrap gap-2 border-t border-ops-border pt-3">
          {plan.can.submit && <button onClick={() => setConfirmSubmit(true)} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg">{a.status === 'REJECTED' ? 'Resubmit for approval' : 'Submit for approval'}</button>}
          {plan.can.decide && (
            <>
              <button onClick={() => { setDecision('approve'); setDecisionError(''); }} className="rounded-md bg-ops-success px-3 py-1.5 text-xs font-semibold text-ops-bg">Approve</button>
              <button onClick={() => { setDecision('reject'); setDecisionError(''); }} className="rounded-md border border-ops-danger/60 px-3 py-1.5 text-xs font-semibold text-ops-danger">Reject</button>
            </>
          )}
          {a.status === 'PENDING' && !plan.can.decide && <p className="text-xs text-ops-textDim">Waiting for {a.authority?.name ?? 'the authority'} to decide.</p>}
        </div>
      </Card>

      <Card n={8} title="MRM assignee and MRM status">
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="MRM assignee">{plan.mrm_assignee ? `${plan.mrm_assignee.rank} ${plan.mrm_assignee.name}` : null}</Field>
          <Field label="MRM preparation"><span className={`rounded-full px-2 py-0.5 text-xs font-medium ${MRM_BADGE[mrm.status]}`}>{mrm.label}</span></Field>
          <Field label="MRM form">{mrm.form_id ? <Link to={`/mrm/${mrm.form_id}`} className="text-ops-accent hover:underline">MRM {mrm.mrm_number} →</Link> : null}</Field>
        </div>
        <p className="text-xs text-ops-textDim">MRM preparation is tracked separately from mission approval — approving the mission does not complete the MRM, and vice versa.</p>
        {plan.can.prepare_mrm && (
          <Link to={`/mrm/new?mission=${plan.id}`} className="inline-block rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg">Prepare the MRM for this mission</Link>
        )}
      </Card>

      <Card n={9} title="Notifications and activity history">
        {activity === null ? <p className="text-sm text-ops-textDim">Loading…</p> : activity.length === 0 ? <p className="text-sm text-ops-textDim">No activity yet.</p> : (
          <ol className="space-y-2">
            {activity.map((e, i) => (
              <li key={i} className="border-l-2 border-ops-border pl-3 text-xs">
                <p className="text-ops-text">{e.title}</p>
                <p className="text-ops-textDim">{e.actor} · {formatDateTime(e.when)}{e.kind === 'notification' ? ` · ${e.detail}` : ''}</p>
                {e.kind !== 'notification' && e.detail && <p className="italic text-ops-textDim">“{e.detail}”</p>}
              </li>
            ))}
          </ol>
        )}
      </Card>

      {decision && (
        <Modal title={decision === 'approve' ? `Approve “${plan.name}”` : `Reject “${plan.name}”`} onClose={() => setDecision(null)}>
          <div className="space-y-3">
            <TextAreaField label={decision === 'approve' ? 'Comments (optional)' : 'Reason for rejection'} required={decision === 'reject'} rows={4}
                           value={comments} error={decisionError || undefined} onChange={(v) => { setComments(v); setDecisionError(''); }} />
            <div className="flex justify-end gap-2">
              <button onClick={() => setDecision(null)} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-textDim">Cancel</button>
              <button disabled={busy} onClick={decide} className={`rounded-md px-3 py-1.5 text-xs font-semibold disabled:opacity-50 ${decision === 'approve' ? 'bg-ops-success text-ops-bg' : 'bg-ops-danger text-white'}`}>
                {busy ? 'Saving…' : decision === 'approve' ? 'Approve mission' : 'Reject mission'}
              </button>
            </div>
          </div>
        </Modal>
      )}
      {confirmSubmit && (
        <ConfirmDialog title="Submit for approval" confirmLabel="Submit" isBusy={busy} onConfirm={submit} onCancel={() => setConfirmSubmit(false)}
                       message={`Submit this mission to ${a.authority?.name ?? 'the selected authority'}? The mission will be locked for editing while it awaits a decision, and the MRM assignee will be asked to prepare the MRM.`} />
      )}
    </div>
  );
}
