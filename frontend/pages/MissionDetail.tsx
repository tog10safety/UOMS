import { FormEvent, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { missionsApi, personnelApi, unitsApi } from '@/api/endpoints';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import RecordFormModal from '@/components/common/RecordForm';
import RiskLevelBadge from '@/components/common/RiskLevelBadge';
import { buildMissionFields, hazardFields } from '@/components/missions/missionFields';
import { PercentBar, StageBadge } from '@/components/mrm/MrmBadges';
import { useMrmMe } from '@/components/mrm/useMrm';
import { useAuth } from '@/contexts/AuthContext';
import { useToast } from '@/contexts/ToastContext';
import type {
  HazardAssessment,
  HazardCategory,
  MissionDetail as MissionDetailType,
  PersonnelListItem,
  RiskProbability,
  RiskSeverity,
  Unit,
} from '@/types';

const CATEGORY_OPTIONS: HazardCategory[] = [
  'WEATHER', 'MECHANICAL', 'HUMAN_ERROR', 'ENEMY_ACTION', 'TERRAIN', 'MEDICAL', 'OTHER',
];
const PROBABILITY_OPTIONS: { value: RiskProbability; label: string }[] = [
  { value: 'FREQUENT', label: 'Frequent (A)' },
  { value: 'LIKELY', label: 'Likely (B)' },
  { value: 'OCCASIONAL', label: 'Occasional (C)' },
  { value: 'SELDOM', label: 'Seldom (D)' },
  { value: 'UNLIKELY', label: 'Unlikely (E)' },
];
const SEVERITY_OPTIONS: { value: RiskSeverity; label: string }[] = [
  { value: 'CATASTROPHIC', label: 'Catastrophic (I)' },
  { value: 'CRITICAL', label: 'Critical (II)' },
  { value: 'MODERATE', label: 'Moderate (III)' },
  { value: 'NEGLIGIBLE', label: 'Negligible (IV)' },
];

const emptyHazardForm = {
  hazard_description: '',
  category: 'OTHER' as HazardCategory,
  probability: 'OCCASIONAL' as RiskProbability,
  severity: 'MODERATE' as RiskSeverity,
  existing_controls: '',
  additional_controls: '',
};

export default function MissionDetail() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const mrmMe = useMrmMe();
  const { showSuccess, showError } = useToast();
  const navigate = useNavigate();
  const [units, setUnits] = useState<Unit[]>([]);
  const [personnel, setPersonnel] = useState<PersonnelListItem[]>([]);
  const [editingMission, setEditingMission] = useState(false);
  const [editingHazard, setEditingHazard] = useState<HazardAssessment | null>(null);
  const [pendingHazardDelete, setPendingHazardDelete] = useState<HazardAssessment | null>(null);
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [approveComment, setApproveComment] = useState('');
  const [mission, setMission] = useState<MissionDetailType | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [hazardForm, setHazardForm] = useState(emptyHazardForm);
  const [isSubmittingHazard, setIsSubmittingHazard] = useState(false);
  const [rejectComment, setRejectComment] = useState('');
  const [showRejectBox, setShowRejectBox] = useState(false);
  const [workflowBusy, setWorkflowBusy] = useState(false);

  const canWrite = can('MISSIONS', 'EDIT');
  const canApprove = can('MISSIONS', 'APPROVE');
  const canDelete = can('MISSIONS', 'DELETE');
  // Once a mission has an MRM form, the MRM owns hazards & approval; this legacy list becomes read-only.
  const legacyEditable = !mission?.mrm;

  const load = () => {
    if (!id) return Promise.resolve();
    return missionsApi
      .get(id)
      .then((data) => setMission(data))
      .catch(() => setError('Unable to load mission.'));
  };

  useEffect(() => {
    setIsLoading(true);
    load().finally(() => setIsLoading(false));
  }, [id]);

  useEffect(() => {
    unitsApi.list().then((d) => setUnits(d.results.filter((u) => u.is_active))).catch(() => {});
    personnelApi.list({ page_size: 200 }).then((d) => setPersonnel(d.results)).catch(() => {});
  }, []);

  const deleteHazard = async () => {
    if (!pendingHazardDelete) return;
    setConfirmBusy(true);
    try {
      await missionsApi.deleteHazard(pendingHazardDelete.id);
      showSuccess('Hazard removed.');
      setPendingHazardDelete(null);
      await load();
    } catch {
      showError('Unable to remove hazard.');
    } finally {
      setConfirmBusy(false);
    }
  };

  const archiveMission = async () => {
    if (!id) return;
    setConfirmBusy(true);
    try {
      await missionsApi.archive(id);
      showSuccess('Mission archived.');
      navigate('/missions');
    } catch {
      showError('Unable to archive mission.');
      setConfirmBusy(false);
    }
  };

  const handleAddHazard = async (e: FormEvent) => {
    e.preventDefault();
    if (!id) return;
    setIsSubmittingHazard(true);
    try {
      await missionsApi.addHazard(id, hazardForm);
      setHazardForm(emptyHazardForm);
      await load();
    } catch {
      setError('Unable to add hazard assessment.');
    } finally {
      setIsSubmittingHazard(false);
    }
  };

  const handleSubmitForApproval = async () => {
    if (!id) return;
    setWorkflowBusy(true);
    try {
      await missionsApi.submitForApproval(id);
      await load();
    } catch {
      setError('Unable to submit for approval — at least one hazard assessment is required.');
    } finally {
      setWorkflowBusy(false);
    }
  };

  const handleApprove = async () => {
    if (!id) return;
    setWorkflowBusy(true);
    try {
      await missionsApi.approve(id, approveComment);
      setApproveComment('');
      await load();
    } finally {
      setWorkflowBusy(false);
    }
  };

  const handleReject = async () => {
    if (!id || !rejectComment.trim()) return;
    setWorkflowBusy(true);
    try {
      await missionsApi.reject(id, rejectComment);
      setShowRejectBox(false);
      setRejectComment('');
      await load();
    } finally {
      setWorkflowBusy(false);
    }
  };

  if (isLoading) return <p className="text-sm text-ops-textDim">Loading mission…</p>;
  if (error && !mission) return <p className="text-sm text-ops-danger">{error}</p>;
  if (!mission) return null;

  return (
    <div className="space-y-6">
      <Link to="/missions" className="text-xs text-ops-textDim hover:text-ops-accent">
        ← Back to Missions
      </Link>

      {/* Mission profile */}
      <div className="ops-card p-5">
        <div className="mb-3 flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold text-ops-text">{mission.name}</h2>
            <p className="mt-1 text-sm text-ops-textDim">{mission.description || 'No description provided.'}</p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <RiskLevelBadge level={mission.overall_risk_level} />
            <span className="text-xs text-ops-textDim">Overall Initial Risk</span>
            <div className="flex gap-3">
              {canWrite && (
                <button onClick={() => setEditingMission(true)} className="text-xs font-medium text-ops-textDim hover:text-ops-text">Edit</button>
              )}
              {canDelete && (
                <button onClick={() => setArchiveOpen(true)} className="text-xs font-medium text-ops-danger hover:underline">Archive</button>
              )}
            </div>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4 border-t border-ops-border pt-3 text-sm md:grid-cols-4">
          <div>
            <p className="ops-label">Status</p>
            <p className="text-ops-text">{mission.status}</p>
          </div>
          <div>
            <p className="ops-label">Risk Review</p>
            <p className="text-ops-text">{mission.risk_review_status}</p>
          </div>
          <div>
            <p className="ops-label">Start Date</p>
            <p className="text-ops-text">{mission.start_date ? new Date(mission.start_date).toLocaleString() : '—'}</p>
          </div>
          <div>
            <p className="ops-label">End Date</p>
            <p className="text-ops-text">{mission.end_date ? new Date(mission.end_date).toLocaleString() : '—'}</p>
          </div>
        </div>
      </div>

      {/* MRM form (formal risk assessment & tiered approval) */}
      <div className="ops-card space-y-3 p-5">
        <p className="ops-label">Mission Risk Management (MRM)</p>
        {mission.mrm ? (
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="space-y-1">
              <p className="text-sm text-ops-text">
                MRM <span className="font-mono text-ops-accent">{mission.mrm.mrm_number}</span>{' '}
                <StageBadge stage={mission.mrm.stage as never} />
              </p>
              <PercentBar percent={mission.mrm.total_percent} />
              <p className="text-xs text-ops-textDim">
                Decision authority: <b className="text-ops-text">{mission.mrm.authority_level_label}</b>
                {mission.mrm.authority_name ? ` — ${mission.mrm.authority_name}` : ''}
              </p>
            </div>
            <Link to={`/mrm/${mission.mrm.id}`} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg">Open MRM form →</Link>
          </div>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-ops-textDim">No MRM form yet. The MRM records hazards on the 5×5 matrix and routes approval to the right decision authority.</p>
            {mrmMe?.can_author && (
              <Link to={`/mrm/new?mission=${mission.id}`} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg">Create MRM for this mission</Link>
            )}
          </div>
        )}
      </div>

      {/* Quick approval workflow — superseded by the MRM once one exists */}
      <div className="ops-card p-5">
        <p className="ops-label mb-3">{mission.mrm ? 'Approval History' : 'Quick Approval (without MRM)'}</p>
        {error && <p className="mb-2 text-sm text-ops-danger">{error}</p>}

        {!mission.mrm && (
        <div className="flex flex-wrap items-center gap-3">
          {canWrite && ['DRAFT', 'REJECTED'].includes(mission.risk_review_status) && (
            <button
              disabled={workflowBusy}
              onClick={handleSubmitForApproval}
              className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg disabled:opacity-50"
            >
              Submit for Approval
            </button>
          )}
          {canApprove && mission.risk_review_status === 'SUBMITTED' && (
            <>
              <input
                value={approveComment}
                onChange={(e) => setApproveComment(e.target.value)}
                placeholder="Approval comments (optional)"
                className="w-64 rounded-md border border-ops-border bg-ops-panelLight px-3 py-1.5 text-xs text-ops-text outline-none focus:border-ops-accent"
              />
              <button
                disabled={workflowBusy}
                onClick={handleApprove}
                className="rounded-md border border-ops-success/40 px-3 py-1.5 text-xs font-medium text-ops-success hover:bg-ops-success/10 disabled:opacity-50"
              >
                Approve
              </button>
              <button
                disabled={workflowBusy}
                onClick={() => setShowRejectBox((s) => !s)}
                className="rounded-md border border-ops-danger/40 px-3 py-1.5 text-xs font-medium text-ops-danger hover:bg-ops-danger/10 disabled:opacity-50"
              >
                Reject
              </button>
            </>
          )}
          {mission.risk_review_status === 'APPROVED' && (
            <p className="text-xs text-ops-success">
              Approved by {mission.reviewed_by_name} on{' '}
              {mission.reviewed_at && new Date(mission.reviewed_at).toLocaleString()}
            </p>
          )}
        </div>
        )}

        {!mission.mrm && showRejectBox && (
          <div className="mt-3 space-y-2">
            <textarea
              value={rejectComment}
              onChange={(e) => setRejectComment(e.target.value)}
              placeholder="Reason for rejection (required)…"
              rows={2}
              className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-danger"
            />
            <button
              disabled={workflowBusy || !rejectComment.trim()}
              onClick={handleReject}
              className="rounded-md bg-ops-danger px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
            >
              Confirm Rejection
            </button>
          </div>
        )}

        {mission.approval_logs.length > 0 && (
          <ul className="mt-4 space-y-1 border-t border-ops-border pt-3">
            {mission.approval_logs.map((log) => (
              <li key={log.id} className="text-xs text-ops-textDim">
                <span className="font-medium text-ops-text">{log.action}</span> by {log.actor_name ?? 'system'} —{' '}
                {new Date(log.created_at).toLocaleString()}
                {log.comments && <span className="italic"> — “{log.comments}”</span>}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Hazard assessments */}
      <div className="ops-card overflow-hidden">
        <div className="flex items-center justify-between border-b border-ops-border px-5 py-3">
          <p className="ops-label">Hazard Risk Assessment</p>
          <RiskLevelBadge level={mission.overall_residual_risk_level} />
        </div>
        <table className="w-full text-left text-sm">
          <thead className="bg-ops-panelLight text-xs uppercase tracking-wider text-ops-textDim">
            <tr>
              <th className="px-4 py-2">Hazard</th>
              <th className="px-4 py-2">Category</th>
              <th className="px-4 py-2">P / S</th>
              <th className="px-4 py-2">Initial Risk</th>
              <th className="px-4 py-2">Controls</th>
              <th className="px-4 py-2">Residual Risk</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {mission.hazard_assessments.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-ops-textDim">
                  No hazards identified yet.
                </td>
              </tr>
            )}
            {mission.hazard_assessments.map((h: HazardAssessment) => (
              <tr key={h.id} className="border-t border-ops-border align-top">
                <td className="max-w-xs px-4 py-3 text-ops-text">{h.hazard_description}</td>
                <td className="px-4 py-3 text-xs text-ops-textDim">{h.category.replace('_', ' ')}</td>
                <td className="px-4 py-3 text-xs text-ops-textDim">
                  {h.probability} / {h.severity}
                </td>
                <td className="px-4 py-3">
                  <RiskLevelBadge level={h.initial_risk_level} />
                </td>
                <td className="max-w-xs px-4 py-3 text-xs text-ops-textDim">
                  <p><span className="text-ops-text">Existing:</span> {h.existing_controls || '—'}</p>
                  <p className="mt-1"><span className="text-ops-text">Additional:</span> {h.additional_controls || '—'}</p>
                </td>
                <td className="px-4 py-3">
                  <RiskLevelBadge level={h.residual_risk_level} />
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-right">
                  {canWrite && legacyEditable && (
                    <button onClick={() => setEditingHazard(h)} className="mr-3 text-xs font-medium text-ops-textDim hover:text-ops-text">Edit</button>
                  )}
                  {canDelete && legacyEditable && (
                    <button onClick={() => setPendingHazardDelete(h)} className="text-xs font-medium text-ops-danger hover:underline">Remove</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {!legacyEditable && (
          <p className="border-t border-ops-border p-4 text-xs text-ops-textDim">
            This quick hazard list is read-only because the mission’s risk assessment is owned by its MRM form.{' '}
            <Link to={`/mrm/${mission?.mrm?.id}`} className="text-ops-accent hover:underline">Edit hazards in the MRM →</Link>
          </p>
        )}
        {canWrite && legacyEditable && (
          <form onSubmit={handleAddHazard} className="space-y-3 border-t border-ops-border p-5">
            <p className="ops-label">Add Hazard</p>
            <textarea
              required
              placeholder="Describe the hazard…"
              value={hazardForm.hazard_description}
              onChange={(e) => setHazardForm({ ...hazardForm, hazard_description: e.target.value })}
              rows={2}
              className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
            />
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <select
                value={hazardForm.category}
                onChange={(e) => setHazardForm({ ...hazardForm, category: e.target.value as HazardCategory })}
                className="rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text"
              >
                {CATEGORY_OPTIONS.map((c) => (
                  <option key={c} value={c}>{c.replace('_', ' ')}</option>
                ))}
              </select>
              <select
                value={hazardForm.probability}
                onChange={(e) => setHazardForm({ ...hazardForm, probability: e.target.value as RiskProbability })}
                className="rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text"
              >
                {PROBABILITY_OPTIONS.map((p) => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
              <select
                value={hazardForm.severity}
                onChange={(e) => setHazardForm({ ...hazardForm, severity: e.target.value as RiskSeverity })}
                className="rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text"
              >
                {SEVERITY_OPTIONS.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <textarea
                placeholder="Existing controls…"
                value={hazardForm.existing_controls}
                onChange={(e) => setHazardForm({ ...hazardForm, existing_controls: e.target.value })}
                rows={2}
                className="rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
              />
              <textarea
                placeholder="Additional controls…"
                value={hazardForm.additional_controls}
                onChange={(e) => setHazardForm({ ...hazardForm, additional_controls: e.target.value })}
                rows={2}
                className="rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
              />
            </div>
            <button
              type="submit"
              disabled={isSubmittingHazard}
              className="rounded-md bg-ops-accent px-4 py-2 text-xs font-semibold text-ops-bg disabled:opacity-50"
            >
              {isSubmittingHazard ? 'Adding…' : 'Add Hazard'}
            </button>
          </form>
        )}
      </div>

      {editingMission && (
        <RecordFormModal
          title="Edit Mission"
          width="lg"
          fields={buildMissionFields(units, personnel)}
          record={mission}
          onSubmit={async (body) => {
            await missionsApi.update(mission.id, body);
            showSuccess('Mission updated.');
            setEditingMission(false);
            await load();
          }}
          onClose={() => setEditingMission(false)}
        />
      )}

      {editingHazard && (
        <RecordFormModal
          title="Edit Hazard"
          fields={hazardFields}
          record={editingHazard}
          onSubmit={async (body) => {
            await missionsApi.updateHazard(editingHazard.id, body);
            showSuccess('Hazard updated.');
            setEditingHazard(null);
            await load();
          }}
          onClose={() => setEditingHazard(null)}
        />
      )}

      {pendingHazardDelete && (
        <ConfirmDialog
          title="Remove Hazard"
          message="Remove this hazard assessment from the mission?"
          confirmLabel="Remove"
          danger
          isBusy={confirmBusy}
          onConfirm={deleteHazard}
          onCancel={() => setPendingHazardDelete(null)}
        />
      )}

      {archiveOpen && (
        <ConfirmDialog
          title="Archive Mission"
          message={`Archive "${mission.name}"? It can be restored from the Missions list.`}
          confirmLabel="Archive"
          danger
          isBusy={confirmBusy}
          onConfirm={archiveMission}
          onCancel={() => setArchiveOpen(false)}
        />
      )}
    </div>
  );
}
