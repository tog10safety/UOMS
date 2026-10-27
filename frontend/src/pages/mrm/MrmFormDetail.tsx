import { FormEvent, useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { mrmApi, openBlob, saveBlob } from '@/api/mrmApi';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import { SelectField, TextAreaField, inputClass } from '@/components/common/FormFields';
import Modal from '@/components/common/Modal';
import RecordFormModal, { FieldDef } from '@/components/common/RecordForm';
import { PercentBar, RiskCell, StageBadge } from '@/components/mrm/MrmBadges';
import { useMrmConfig } from '@/components/mrm/useMrm';
import { useToast } from '@/contexts/ToastContext';
import type { MrmDetail, MrmFeedbackItem } from '@/types/mrm';
import { extractApiError, formatDateTime } from '@/utils/errors';

const STEPS = ['Drafted', 'Submitted', 'Evaluator review', 'Decision authority', 'Approved'];

function stepIndex(f: MrmDetail): number {
  if (f.authority_approved) return 4;
  if (f.status === 'draft') return 0;
  if (f.status === 'submitted') return 2;
  return f.review_status === 'approved' ? 3 : 1;
}

const RATING_OPTIONS = [1, 2, 3, 4, 5].map((n) => ({ value: String(n), label: `${n} — ${['Poor', 'Fair', 'Good', 'Very good', 'Excellent'][n - 1]}` }));

const feedbackFields: FieldDef[] = [
  { name: 'risk_assessment_accuracy', label: 'Accuracy of the risk assessment', type: 'select', required: true, defaultValue: '3', options: RATING_OPTIONS },
  { name: 'hazard_identification_rating', label: 'Hazard identification', type: 'select', required: true, defaultValue: '3', options: RATING_OPTIONS },
  { name: 'mitigation_effectiveness', label: 'Effectiveness of mitigations', type: 'select', required: true, defaultValue: '3', options: RATING_OPTIONS, span: 2 },
  { name: 'what_went_well', label: 'What went well', type: 'textarea' },
  { name: 'what_could_be_improved', label: 'What could be improved', type: 'textarea' },
  { name: 'new_hazards_identified', label: 'New hazards encountered', type: 'textarea' },
  { name: 'lessons_learned', label: 'Lessons learned', type: 'textarea' },
  { name: 'additional_comments', label: 'Additional comments', type: 'textarea' },
  { name: 'recommend_add_to_hazard_registry', label: 'Recommend adding a hazard to the registry', type: 'checkbox' },
  { name: 'is_anonymous', label: 'Submit anonymously', type: 'checkbox', help: 'Hidden from reviewers (administrators can still see who you are).' },
  { name: 'recommended_hazard_description', label: 'Recommended hazard', type: 'textarea', help: 'Required if you recommend adding one.' },
  { name: 'recommended_mitigations', label: 'Recommended mitigations', type: 'textarea' },
];

export default function MrmFormDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const config = useMrmConfig();
  const { showSuccess, showError } = useToast();

  const [form, setForm] = useState<MrmDetail | null>(null);
  const [feedback, setFeedback] = useState<MrmFeedbackItem[]>([]);
  const [error, setError] = useState('');
  const [warnings, setWarnings] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const [reviewOpen, setReviewOpen] = useState(false);
  const [approveOpen, setApproveOpen] = useState(false);
  const [reassignOpen, setReassignOpen] = useState(false);
  const [reviewerOpen, setReviewerOpen] = useState(false);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [closeFeedbackOpen, setCloseFeedbackOpen] = useState(false);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const f = await mrmApi.forms.get(id);
      setForm(f);
      if (f.authority_approved) mrmApi.forms.feedback(id).then(setFeedback).catch(() => setFeedback([]));
    } catch (e) {
      setError(extractApiError(e, 'Unable to load this MRM.'));
    }
  }, [id]);

  useEffect(() => { void load(); }, [load]);

  const run = async (action: () => Promise<MrmDetail | void>, success: string) => {
    setBusy(true);
    try {
      const result = await action();
      if (result) { setForm(result); setWarnings(result.warnings ?? []); }
      else await load();
      showSuccess(success);
    } catch (e) {
      showError(extractApiError(e));
    } finally {
      setBusy(false);
    }
  };

  const viewPdf = async () => {
    try { const { blob } = await mrmApi.forms.pdf(id!); openBlob(blob); } catch (e) { showError(extractApiError(e, 'Unable to open the PDF.')); }
  };
  const downloadPdf = async () => {
    try { const { blob, filename } = await mrmApi.forms.pdf(id!); saveBlob(blob, filename === 'download' ? `MRM_${form?.mrm_number}.pdf` : filename); }
    catch (e) { showError(extractApiError(e, 'Unable to download the PDF.')); }
  };

  if (error) return <div className="ops-card p-6 text-sm text-ops-danger">{error} <Link to="/mrm" className="ml-2 text-ops-accent">← Back</Link></div>;
  if (!form || !config) return <p className="text-sm text-ops-textDim">Loading…</p>;

  const can = form.can;
  const current = stepIndex(form);
  const rejected = form.status === 'reviewed' && (form.review_status === 'rejected' || form.review_status === 'needs_revision');

  return (
    <div className="space-y-5">
      <Link to="/mrm" className="text-xs text-ops-textDim hover:text-ops-accent">← All MRM forms</Link>

      {/* header */}
      <div className="ops-card space-y-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="font-mono text-xs text-ops-accent">MRM {form.mrm_number}</p>
            <h1 className="text-xl font-semibold text-ops-text">{form.activity_mission}</h1>
            <p className="mt-1 text-xs text-ops-textDim">
              {form.unit_name} · created by {form.creator_name} · {formatDateTime(form.created_at)}
              {form.mission && <> · <Link to={`/missions/${form.mission}`} className="text-ops-accent hover:underline">⚑ {form.mission_name}</Link></>}
            </p>
          </div>
          <div className="space-y-2 text-right">
            <StageBadge stage={form.stage} />
            <div className="flex justify-end"><PercentBar percent={form.risk.total_percent} /></div>
            <p className="text-xs text-ops-textDim">Decision: <b className="text-ops-text">{form.risk.authority_level_label}</b> ({form.risk.authority_range})</p>
          </div>
        </div>

        {/* progress */}
        <ol className="flex flex-wrap items-center gap-2 text-xs">
          {STEPS.map((label, i) => (
            <li key={label} className="flex items-center gap-2">
              <span className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold ${
                i < current || (i === 4 && form.authority_approved) ? 'bg-ops-success text-ops-bg' : i === current ? (rejected && i === 1 ? 'bg-ops-danger text-white' : 'bg-ops-accent text-ops-bg') : 'bg-ops-panelLight text-ops-textDim'}`}>
                {i < current ? '✓' : i + 1}
              </span>
              <span className={i === current ? 'text-ops-text' : 'text-ops-textDim'}>{label}</span>
              {i < STEPS.length - 1 && <span className="text-ops-border">—</span>}
            </li>
          ))}
        </ol>

        {warnings.map((w) => <p key={w} className="rounded-md border border-ops-warning/40 bg-ops-warning/10 p-2 text-xs text-ops-warning">{w}</p>)}
        {rejected && form.review_notes && (
          <p className="rounded-md border border-ops-danger/40 bg-ops-danger/10 p-3 text-sm text-ops-text">
            <b className="text-ops-danger">{form.review_status === 'rejected' ? 'Rejected' : 'Revision requested'} by {form.reviewer_name}:</b> {form.review_notes}
          </p>
        )}
        {form.stage === 'needs_authority_assignment' && (
          <p className="rounded-md border border-ops-danger/40 bg-ops-danger/10 p-3 text-sm text-ops-text">
            Nobody currently holds the <b>{form.risk.authority_level_label}</b> designation in this unit or its mother units. {can.reassign_authority ? 'Assign an approver below.' : 'An administrator or Unit Safety Officer must assign an approver.'}
          </p>
        )}

        {/* actions */}
        <div className="flex flex-wrap gap-2 border-t border-ops-border pt-4">
          {can.edit && <Link to={`/mrm/${form.id}/edit`} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-text hover:border-ops-accent">{can.is_resubmission ? 'Revise' : 'Edit'}</Link>}
          {can.submit && (
            <button disabled={busy} onClick={() => run(() => mrmApi.forms.submit(form.id), can.is_resubmission ? 'Resubmitted for review.' : 'Submitted for review.')}
                    className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg">{can.is_resubmission ? 'Resubmit for review' : 'Submit for review'}</button>
          )}
          {can.review && <button onClick={() => setReviewOpen(true)} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg">Review</button>}
          {can.authority_approve && <button onClick={() => setApproveOpen(true)} className="rounded-md bg-ops-success px-3 py-1.5 text-xs font-semibold text-ops-bg">Approve as {form.risk.authority_level_label}</button>}
          {can.sign && <button disabled={busy} onClick={() => run(() => mrmApi.forms.sign(form.id), 'Signed.')} className="rounded-md border border-ops-accent px-3 py-1.5 text-xs text-ops-accent">Apply my signature ({can.sign})</button>}
          {can.reassign_authority && <button onClick={() => setReassignOpen(true)} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-text">{form.authority ? 'Change approver' : 'Assign approver'}</button>}
          {can.reassign_reviewer && <button onClick={() => setReviewerOpen(true)} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-text">Reassign reviewer</button>}
          <button onClick={viewPdf} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-text">{form.authority_approved ? 'View PDF' : 'Preview PDF'}</button>
          <button onClick={downloadPdf} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-text">Download PDF</button>
          {can.regenerate_pdf && form.authority_approved && (
            <button disabled={busy} onClick={() => run(() => mrmApi.forms.regeneratePdf(form.id), 'PDF regenerated.')} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-textDim">Regenerate PDF</button>
          )}
          {can.give_feedback && <button onClick={() => setFeedbackOpen(true)} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg">Give feedback</button>}
          {can.delete && <button onClick={() => setArchiveOpen(true)} className="ml-auto rounded-md border border-ops-danger/50 px-3 py-1.5 text-xs text-ops-danger">Delete</button>}
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          {/* objectives */}
          <section className="ops-card space-y-3 p-5">
            <p className="ops-label">Objective &amp; conditions</p>
            <Info label="Safety objectives" value={form.safety_objectives} />
            <div className="grid gap-3 md:grid-cols-2">
              <Info label="Aircraft / Vehicle" value={form.aircraft_vehicle || '—'} />
              <Info label="Mission statement" value={form.mission_statement || '—'} />
              <Info label="Environment" value={form.environment || '—'} />
              <Info label="I’M SAFE" value={Object.keys(config.imsafe_checklist).every((k) => form.imsafe[k]) ? 'All items confirmed' : 'Not fully confirmed'} />
            </div>
          </section>

          {/* hazards */}
          <section className="ops-card overflow-x-auto">
            <p className="ops-label border-b border-ops-border px-5 py-3">Hazards ({form.hazards.length})</p>
            <table className="w-full text-left text-sm">
              <thead className="bg-ops-panelLight text-xs uppercase tracking-wider text-ops-textDim">
                <tr><th className="px-4 py-2">Hazard</th><th className="px-4 py-2">Before</th><th className="px-4 py-2">Mitigations</th><th className="px-4 py-2">Residual</th></tr>
              </thead>
              <tbody>
                {form.hazards.map((h) => (
                  <tr key={h.id} className="border-t border-ops-border align-top">
                    <td className="px-4 py-3"><p className="text-ops-text">{h.hazard_description}</p><p className="text-[11px] text-ops-textDim">{h.activity_code}</p></td>
                    <td className="px-4 py-3"><RiskCell rating={h.before.rating} level={h.before.level} /></td>
                    <td className="px-4 py-3 text-xs text-ops-textDim">
                      <ul className="list-disc pl-4">{h.mitigations.split('\n').filter(Boolean).map((m, i) => <li key={i}>{m}</li>)}</ul>
                      {h.additional_mitigations && <p className="mt-1 text-ops-text">+ {h.additional_mitigations}</p>}
                    </td>
                    <td className="px-4 py-3">
                      <RiskCell rating={h.residual.rating} level={h.residual.level} />
                      {h.override && <p className="mt-1 text-[10px] text-ops-warning">overridden (registry {h.registry_after.rating})</p>}
                      {h.registry_changed && !form.authority_approved && <p className="mt-1 text-[10px] text-ops-textDim">registry changed since selection</p>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="flex flex-wrap items-center gap-6 border-t border-ops-border px-5 py-3 text-xs text-ops-textDim">
              <span>Residual {form.risk.residual_risk}/{form.risk.max_risk} = <b className="text-ops-text">{form.risk.total_percent.toFixed(1)}%</b></span>
              <span>Category: <b className="text-ops-text">{form.risk.risk_category}</b></span>
            </div>
          </section>

          {/* feedback */}
          {form.authority_approved && (
            <section className="ops-card space-y-3 p-5">
              <div className="flex items-center justify-between">
                <p className="ops-label">Post-mission feedback</p>
                <div className="flex items-center gap-3 text-xs text-ops-textDim">
                  <span>{form.feedback_counts.submitted} submitted · {form.feedback_counts.awaiting} awaited</span>
                  {can.manage_personnel && !form.feedback_collection_closed && (
                    <button onClick={() => setCloseFeedbackOpen(true)} className="text-ops-warning hover:underline">Close collection</button>
                  )}
                  {form.feedback_collection_closed && <span className="text-ops-warning">Collection closed</span>}
                </div>
              </div>
              {feedback.length === 0 && <p className="text-xs text-ops-textDim">No feedback yet.</p>}
              {feedback.map((fb) => (
                <div key={fb.id} className="rounded-md border border-ops-border p-3 text-sm">
                  <div className="flex justify-between text-xs text-ops-textDim">
                    <span>{fb.submitted_by ?? 'Anonymous'} · {formatDateTime(fb.submitted_at)}</span>
                    <span className="uppercase">{fb.status.replace('_', ' ')}</span>
                  </div>
                  <p className="mt-1 font-mono text-xs text-ops-textDim">Accuracy {fb.risk_assessment_accuracy}/5 · Hazards {fb.hazard_identification_rating}/5 · Mitigations {fb.mitigation_effectiveness}/5</p>
                  {fb.what_went_well && <p className="mt-1 text-ops-text"><b>Went well:</b> {fb.what_went_well}</p>}
                  {fb.what_could_be_improved && <p className="text-ops-text"><b>Improve:</b> {fb.what_could_be_improved}</p>}
                  {fb.new_hazards_identified && <p className="text-ops-text"><b>New hazards:</b> {fb.new_hazards_identified}</p>}
                </div>
              ))}
            </section>
          )}
        </div>

        <div className="space-y-5">
          {/* approval chain */}
          <section className="ops-card space-y-3 p-5">
            <p className="ops-label">Approval chain</p>
            <Chain role="Compiled by" name={form.creator_name} signed={form.creator_signed} when={form.creator_signature_date} />
            <Chain role="Reviewed by" name={form.reviewer_name} signed={form.evaluator_signed} when={form.evaluator_signature_date}
                   status={form.status === 'submitted' ? 'Pending review' : form.status === 'reviewed' ? form.review_status.replace('_', ' ') : undefined} />
            <Chain role={`Decision authority (${form.risk.authority_level_label})`} name={form.authority_name || 'Not assigned'} signed={form.authority_approved}
                   when={form.authority_approval_date} status={form.authority_approved ? undefined : form.authority ? 'Pending approval' : undefined} />
          </section>

          {/* personnel */}
          <PersonnelCard form={form} onChange={load} />

          {/* timeline */}
          <section className="ops-card space-y-3 p-5">
            <p className="ops-label">Timeline</p>
            <ol className="space-y-3">
              {[...form.events].reverse().map((e) => (
                <li key={e.id} className="border-l-2 border-ops-border pl-3 text-xs">
                  <p className="text-ops-text">{e.label}</p>
                  <p className="text-ops-textDim">{e.actor || 'System'} · {formatDateTime(e.created_at)}</p>
                  {e.comments && <p className="italic text-ops-textDim">“{e.comments}”</p>}
                </li>
              ))}
            </ol>
          </section>
        </div>
      </div>

      {reviewOpen && <ReviewModal form={form} onClose={() => setReviewOpen(false)}
                                  onDone={(f) => { setForm(f); setWarnings(f.warnings ?? []); setReviewOpen(false); showSuccess('Review recorded.'); }} />}
      {approveOpen && <ApproveModal form={form} onClose={() => setApproveOpen(false)}
                                    onDone={(f) => { setForm(f); setWarnings(f.warnings ?? []); setApproveOpen(false); showSuccess('MRM approved.'); void load(); }} />}
      {reassignOpen && <ReassignModal form={form} onClose={() => setReassignOpen(false)}
                                      onDone={(f) => { setForm(f); setReassignOpen(false); showSuccess('Decision authority assigned.'); }} />}
      {reviewerOpen && <ReassignReviewerModal form={form} onClose={() => setReviewerOpen(false)}
                                              onDone={(f) => { setForm(f); setReviewerOpen(false); showSuccess('Reviewer reassigned.'); }} />}
      {feedbackOpen && (
        <RecordFormModal title={`Feedback — MRM ${form.mrm_number}`} width="lg" fields={feedbackFields} submitLabel="Submit feedback"
          onSubmit={async (body) => { await mrmApi.forms.giveFeedback(form.id, body); showSuccess('Thank you — feedback submitted.'); setFeedbackOpen(false); await load(); }}
          onClose={() => setFeedbackOpen(false)} />
      )}
      {archiveOpen && (
        <ConfirmDialog title="Delete MRM" message={`Delete MRM ${form.mrm_number}? It will be archived and removed from active lists.`} confirmLabel="Delete" danger isBusy={busy}
          onConfirm={async () => { setBusy(true); try { await mrmApi.forms.archive(form.id); showSuccess('MRM deleted.'); navigate('/mrm'); } catch (e) { showError(extractApiError(e)); setBusy(false); } }}
          onCancel={() => setArchiveOpen(false)} />
      )}
      {closeFeedbackOpen && (
        <ConfirmDialog title="Close feedback collection" message="Tagged personnel will no longer be able to submit feedback for this MRM." confirmLabel="Close collection" isBusy={busy}
          onConfirm={async () => { setCloseFeedbackOpen(false); await run(() => mrmApi.forms.closeFeedback(form.id), 'Feedback collection closed.'); }}
          onCancel={() => setCloseFeedbackOpen(false)} />
      )}
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return <div><p className="text-[10px] uppercase tracking-wider text-ops-textDim">{label}</p><p className="whitespace-pre-wrap text-sm text-ops-text">{value}</p></div>;
}

function Chain({ role, name, signed, when, status }: { role: string; name: string; signed: boolean; when: string | null; status?: string }) {
  return (
    <div className="flex items-start justify-between gap-3 text-sm">
      <div><p className="text-[10px] uppercase tracking-wider text-ops-textDim">{role}</p><p className="text-ops-text">{name || '—'}</p></div>
      <div className="text-right text-xs">
        {signed ? <p className="text-ops-success">✓ Signed</p> : <p className="text-ops-textDim">{status ?? 'Not signed'}</p>}
        {signed && when && <p className="text-ops-textDim">{formatDateTime(when)}</p>}
      </div>
    </div>
  );
}

function ReviewModal({ form, onClose, onDone }: { form: MrmDetail; onClose: () => void; onDone: (f: MrmDetail) => void }) {
  const [decision, setDecision] = useState('approved');
  const [notes, setNotes] = useState('');
  const [autoSign, setAutoSign] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try { onDone(await mrmApi.forms.review(form.id, { review_status: decision, review_notes: notes, auto_sign: autoSign })); }
    catch (err) { setError(extractApiError(err)); setSaving(false); }
  };

  return (
    <Modal title={`Review MRM ${form.mrm_number}`} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <SelectField label="Decision" required value={decision} onChange={setDecision}
                     options={[{ value: 'approved', label: 'Approve — pass to decision authority' }, { value: 'needs_revision', label: 'Needs revision — return to creator' }, { value: 'rejected', label: 'Reject' }]} />
        <TextAreaField label={decision === 'approved' ? 'Notes (optional)' : 'What must change (required)'} required={decision !== 'approved'} rows={4} value={notes} onChange={setNotes} />
        {decision === 'approved' && (
          <label className="flex items-center gap-2 text-sm text-ops-text">
            <input type="checkbox" checked={autoSign} onChange={(e) => setAutoSign(e.target.checked)} className="rounded border-ops-border" /> Apply my signature
          </label>
        )}
        {error && <p className="text-xs text-ops-danger">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-textDim">Cancel</button>
          <button disabled={saving} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg disabled:opacity-50">{saving ? 'Saving…' : 'Submit decision'}</button>
        </div>
      </form>
    </Modal>
  );
}

function ApproveModal({ form, onClose, onDone }: { form: MrmDetail; onClose: () => void; onDone: (f: MrmDetail) => void }) {
  const [comments, setComments] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  return (
    <Modal title={`Approve MRM ${form.mrm_number}`} onClose={onClose}>
      <div className="space-y-3">
        <p className="text-sm text-ops-textDim">
          You are approving this mission as <b className="text-ops-text">{form.risk.authority_level_label}</b> at <b className="text-ops-text">{form.risk.total_percent.toFixed(1)}%</b> residual risk.
          Your signature will be applied and the record locked.
        </p>
        <input value={comments} onChange={(e) => setComments(e.target.value)} placeholder="Comments (optional)" className={inputClass} />
        {error && <p className="text-xs text-ops-danger">{error}</p>}
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-textDim">Cancel</button>
          <button disabled={saving} onClick={async () => { setSaving(true); try { onDone(await mrmApi.forms.approve(form.id, comments)); } catch (e) { setError(extractApiError(e)); setSaving(false); } }}
                  className="rounded-md bg-ops-success px-3 py-1.5 text-xs font-semibold text-ops-bg disabled:opacity-50">{saving ? 'Approving…' : 'Approve & sign'}</button>
        </div>
      </div>
    </Modal>
  );
}

function ReassignModal({ form, onClose, onDone }: { form: MrmDetail; onClose: () => void; onDone: (f: MrmDetail) => void }) {
  const [data, setData] = useState<{ required: string; candidates: { id: string; name: string; unit: string | null }[] } | null>(null);
  const [choice, setChoice] = useState('');
  const [error, setError] = useState('');
  useEffect(() => { mrmApi.forms.authorityCandidates(form.id).then(setData).catch((e) => setError(extractApiError(e))); }, [form.id]);

  const save = async (authority?: string) => {
    try { onDone(await mrmApi.forms.reassignAuthority(form.id, authority)); } catch (e) { setError(extractApiError(e)); }
  };
  return (
    <Modal title="Assign decision authority" onClose={onClose}>
      <div className="space-y-3">
        <p className="text-xs text-ops-textDim">Required designation: <b className="text-ops-text">{data?.required ?? form.risk.authority_level_label}</b></p>
        <SelectField label="Approver" value={choice} onChange={setChoice} options={(data?.candidates ?? []).map((c) => ({ value: c.id, label: `${c.name}${c.unit ? ` (${c.unit})` : ''}` }))}
                     help={data && data.candidates.length === 0 ? 'No user holds this designation. Set “MRM designation” on a user in User Management first.' : undefined} />
        {error && <p className="text-xs text-ops-danger">{error}</p>}
        <div className="flex justify-between">
          <button onClick={() => save()} className="text-xs text-ops-accent hover:underline">Re-run automatic assignment</button>
          <div className="flex gap-2">
            <button onClick={onClose} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-textDim">Cancel</button>
            <button disabled={!choice} onClick={() => save(choice)} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg disabled:opacity-50">Assign</button>
          </div>
        </div>
      </div>
    </Modal>
  );
}

function ReassignReviewerModal({ form, onClose, onDone }: { form: MrmDetail; onClose: () => void; onDone: (f: MrmDetail) => void }) {
  const [options, setOptions] = useState<{ id: string; name: string; unit: string | null }[]>([]);
  const [choice, setChoice] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    mrmApi.forms.evaluators(form.unit).then((list) => setOptions(list.filter((e) => e.id !== form.reviewer?.id))).catch((e) => setError(extractApiError(e)));
  }, [form.unit, form.reviewer?.id]);
  return (
    <Modal title="Reassign reviewer" onClose={onClose}>
      <div className="space-y-3">
        <p className="text-xs text-ops-textDim">Current reviewer: <b className="text-ops-text">{form.reviewer_name}</b>. Only possible while the form is awaiting review.</p>
        <SelectField label="New evaluator" required value={choice} onChange={setChoice} options={options.map((o) => ({ value: o.id, label: `${o.name}${o.unit ? ` (${o.unit})` : ''}` }))} />
        {error && <p className="text-xs text-ops-danger">{error}</p>}
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-textDim">Cancel</button>
          <button disabled={!choice} onClick={async () => { try { onDone(await mrmApi.forms.reassignReviewer(form.id, choice)); } catch (e) { setError(extractApiError(e)); } }}
                  className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg disabled:opacity-50">Reassign</button>
        </div>
      </div>
    </Modal>
  );
}

function PersonnelCard({ form, onChange }: { form: MrmDetail; onChange: () => void }) {
  const { showSuccess, showError } = useToast();
  const config = useMrmConfig();
  const [q, setQ] = useState('');
  const [results, setResults] = useState<{ id: string; name: string; service_number: string; username: string }[]>([]);
  const [role, setRole] = useState('Crew Member');
  const [pending, setPending] = useState<{ user: string; name: string }[] | null>(null);

  useEffect(() => {
    if (!form.can.manage_personnel || q.trim().length < 2) { setResults([]); return; }
    const timer = setTimeout(() => mrmApi.forms.people(q.trim(), form.unit).then(setResults).catch(() => setResults([])), 250);
    return () => clearTimeout(timer);
  }, [q, form.unit, form.can.manage_personnel]);

  const tag = async (userId: string) => {
    try { await mrmApi.forms.tag(form.id, userId, role); setQ(''); setResults([]); showSuccess('Personnel tagged.'); onChange(); }
    catch (e) { showError(extractApiError(e)); }
  };
  const untag = async (tagId: string) => {
    try { await mrmApi.forms.untag(form.id, tagId); onChange(); } catch (e) { showError(extractApiError(e)); }
  };
  const remind = async () => {
    try { setPending((await mrmApi.forms.remind(form.id)).pending); } catch (e) { showError(extractApiError(e)); }
  };

  const tagged = new Set(form.tagged_personnel.map((t) => t.user));
  return (
    <section className="ops-card space-y-3 p-5">
      <div className="flex items-center justify-between">
        <p className="ops-label">Crew &amp; personnel ({form.tagged_personnel.length})</p>
        {form.authority_approved && form.can.manage_personnel && <button onClick={remind} className="text-xs text-ops-accent hover:underline">Who owes feedback?</button>}
      </div>
      {form.tagged_personnel.length === 0 && <p className="text-xs text-ops-textDim">No one tagged.</p>}
      {form.tagged_personnel.map((t) => (
        <div key={t.id} className="flex items-center justify-between text-sm">
          <span className="text-ops-text">{t.name} <i className="text-xs text-ops-textDim">· {t.role}</i></span>
          <span className="flex items-center gap-3 text-xs">
            {form.authority_approved && <span className={t.feedback_submitted ? 'text-ops-success' : 'text-ops-textDim'}>{t.feedback_submitted ? 'feedback ✓' : 'awaiting'}</span>}
            {form.can.manage_personnel && <button onClick={() => untag(t.id)} className="text-ops-danger hover:underline">Remove</button>}
          </span>
        </div>
      ))}
      {form.can.manage_personnel && (
        <div className="space-y-2 border-t border-ops-border pt-3">
          <div className="flex gap-2">
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Tag someone from this unit…" className={inputClass} />
            <select value={role} onChange={(e) => setRole(e.target.value)} className={`${inputClass} max-w-[8rem]`}>
              {(config?.personnel_roles ?? ['Crew Member']).map((r) => <option key={r}>{r}</option>)}
            </select>
          </div>
          {results.filter((r) => !tagged.has(r.id)).map((r) => (
            <button key={r.id} onClick={() => tag(r.id)} className="flex w-full justify-between rounded-md border border-ops-border px-3 py-1.5 text-left text-xs hover:bg-ops-panelLight">
              <span className="text-ops-text">{r.name}</span><span className="text-ops-textDim">{r.service_number || r.username}</span>
            </button>
          ))}
        </div>
      )}
      {pending && (
        <Modal title="Feedback still awaited" onClose={() => setPending(null)}>
          {pending.length === 0 ? <p className="text-sm text-ops-textDim">Everyone tagged has responded.</p> : (
            <ul className="space-y-1 text-sm text-ops-text">{pending.map((p) => <li key={p.user}>• {p.name}</li>)}</ul>
          )}
        </Modal>
      )}
    </section>
  );
}
