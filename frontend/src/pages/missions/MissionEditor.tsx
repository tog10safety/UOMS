import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { gisApi } from '@/api/endpoints';
import { missionOpsApi } from '@/api/missionOps';
import type { KnownPlace } from '@/components/missions/LocationPicker';
import { CATEGORY_MODULES } from '@/components/missions/categories';
import { useToast } from '@/contexts/ToastContext';
import type { CategoryInfo, MissionCategoryKey, MissionPlan, RoleOption } from '@/types/missionOps';
import { errorsFromAxios, firstErrorKey, type FieldErrors } from '@/utils/formErrors';

const newToken = () =>
  (typeof crypto !== 'undefined' && 'randomUUID' in crypto)
    ? crypto.randomUUID()
    : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => { const r = (Math.random() * 16) | 0; return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16); });

export default function MissionEditor() {
  const { id } = useParams();
  const [query] = useSearchParams();
  const navigate = useNavigate();
  const { showSuccess, showError } = useToast();

  const [catalog, setCatalog] = useState<{ categories: CategoryInfo[]; roles: RoleOption[] } | null>(null);
  const [category, setCategory] = useState<MissionCategoryKey | null>((query.get('category') as MissionCategoryKey) || null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [state, setState] = useState<any>(null);
  const [plan, setPlan] = useState<MissionPlan | null>(null);
  const [loading, setLoading] = useState(!!id);
  const [loadError, setLoadError] = useState('');
  const [errors, setErrorsState] = useState<FieldErrors>({});
  const [knownPlaces, setKnownPlaces] = useState<KnownPlace[]>([]);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const token = useRef(newToken());          // idempotency token: a repeated create returns the same mission
  const [savedId, setSavedId] = useState<string | null>(id ?? null);

  const setErrors = (updater: (e: FieldErrors) => FieldErrors) => setErrorsState((e) => updater(e));
  const mod = category ? CATEGORY_MODULES[category] : null;

  useEffect(() => { missionOpsApi.categories().then(setCatalog).catch(() => setLoadError('Unable to load mission categories.')); }, []);

  useEffect(() => {
    gisApi.overlay().then((o) => {
      setKnownPlaces([
        ...o.checkpoints.map((c) => ({ id: `cp-${c.id}`, name: c.name, kind: 'Checkpoint', lat: c.lat, lng: c.lng, mgrs: c.mgrs ?? '' })),
        ...o.landing_zones.map((z) => ({ id: `lz-${z.id}`, name: z.name, kind: 'Landing zone', lat: z.lat, lng: z.lng, mgrs: z.mgrs ?? '' })),
      ]);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!id) return;
    (async () => {
      try {
        const p = await missionOpsApi.get(id);
        if (!p.category) { setLoadError('This mission was created before mission categories existed, so it cannot be edited in this form. Edit it from the Missions list.'); return; }
        const ready = new Set((await missionOpsApi.mrmCandidates(id).catch(() => [])).map((x) => x.id));
        setPlan(p);
        setCategory(p.category);
        setState(CATEGORY_MODULES[p.category].hydrate(p, ready));
      } catch (e) {
        setLoadError(errorsFromAxios(e, 'Unable to load this mission.')._general ?? 'Unable to load this mission.');
      } finally { setLoading(false); }
    })();
  }, [id]);

  const chooseCategory = (key: MissionCategoryKey) => {
    setCategory(key);
    setState(CATEGORY_MODULES[key].empty());
    setErrorsState({});
  };

  const fieldOrder = useMemo(() => ['name', 'start_date', 'end_date', 'unit', 'responsible_section', 'personnel', 'approval_authority', 'mrm_assignee'], []);
  const showErrors = (e: FieldErrors) => {
    setErrorsState(e);
    const key = firstErrorKey(e, fieldOrder);
    if (key) {
      const base = key.split(/[.[]/)[0];
      setTimeout(() => (document.getElementById(`field-${base}`) ?? document.getElementById('form-top'))?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 0);
    }
  };

  const persist = async (forSubmit: boolean): Promise<MissionPlan | null> => {
    if (!mod || !category) return null;
    const problems = mod.validate(state, { forSubmit });
    if (Object.keys(problems).length) { showErrors(problems); return null; }
    setErrorsState({});
    const body = mod.payload(state, savedId ? undefined : token.current);
    const saved = savedId ? await missionOpsApi.update(savedId, body) : await missionOpsApi.create(body);
    setSavedId(saved.id);
    return saved;
  };

  const run = async (forSubmit: boolean) => {
    if (savingRef.current) return;                 // a double click can never send two requests
    savingRef.current = true;
    setSaving(true);
    try {
      const saved = await persist(forSubmit);
      if (!saved) return;
      if (forSubmit) {
        try {
          const submitted = await missionOpsApi.submit(saved.id);
          showSuccess(submitted.newly_submitted === false ? 'This mission was already submitted.' : 'Mission submitted. The approving authority and the MRM assignee have been notified.');
        } catch (e) {
          // The mission itself is saved; keep the user on the form (now in edit mode) with the reason shown beside the field.
          showErrors(errorsFromAxios(e, 'The mission was saved but could not be submitted.'));
          showError('Saved as a draft, but it could not be submitted yet.');
          return;
        }
      } else {
        showSuccess('Mission saved as a draft.');
      }
      navigate(`/missions/${saved.id}`);
    } catch (e) {
      showErrors(errorsFromAxios(e, 'Unable to save the mission.'));
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  if (loadError) return <div className="ops-card p-6 text-sm text-ops-danger">{loadError} <Link to="/missions" className="ml-2 text-ops-accent">← Missions</Link></div>;
  if (loading || !catalog) return <p className="text-sm text-ops-textDim">Loading…</p>;
  if (plan && !plan.can.edit) {
    return (
      <div className="ops-card space-y-2 p-6">
        <p className="text-sm text-ops-text">This mission can no longer be edited — it is {plan.approval.status_label.toLowerCase()}.</p>
        <Link to={`/missions/${plan.id}`} className="text-xs text-ops-accent hover:underline">← Back to the mission</Link>
      </div>
    );
  }

  const isEdit = !!savedId;
  const Form = mod?.Form;

  return (
    <div className="space-y-5">
      <div id="form-top">
        <Link to={isEdit ? `/missions/${savedId}` : '/missions'} className="text-xs text-ops-textDim hover:text-ops-accent">← {isEdit ? 'Mission' : 'Missions'}</Link>
        <h1 className="text-lg font-semibold text-ops-text">{isEdit ? 'Edit mission' : 'New mission'}</h1>
        {plan?.approval.status === 'REJECTED' && plan.approval.comments && (
          <p className="mt-2 rounded-md border border-ops-danger/40 bg-ops-danger/10 p-3 text-sm text-ops-text">
            <b className="text-ops-danger">Rejected by {plan.approval.decided_by_name}:</b> {plan.approval.comments}
          </p>
        )}
      </div>

      {/* step 1 — category */}
      {!category && (
        <section className="space-y-3">
          <p className="ops-label">Choose the mission category</p>
          <div className="grid gap-3 md:grid-cols-2">
            {catalog.categories.map((c) => (
              <button key={c.key} type="button" disabled={!c.enabled} onClick={() => chooseCategory(c.key)}
                      className={`ops-card p-5 text-left transition-colors ${c.enabled ? 'hover:border-ops-accent' : 'cursor-not-allowed opacity-60'}`}>
                <p className="text-base font-semibold text-ops-text">{c.label}</p>
                <p className="mt-1 text-xs text-ops-textDim">{c.description}</p>
                {!c.enabled && <p className="mt-2 text-[11px] font-semibold uppercase tracking-wider text-ops-warning">Coming soon — form pending requirements</p>}
              </button>
            ))}
          </div>
        </section>
      )}

      {category && Form && mod && (
        <>
          <div className="flex items-center gap-3 text-sm">
            <span className="rounded-full bg-ops-accent/10 px-3 py-1 text-xs font-semibold text-ops-accent">{catalog.categories.find((c) => c.key === category)?.label}</span>
            {!isEdit && catalog.categories.filter((c) => c.enabled).length > 1 && (
              <button type="button" onClick={() => { setCategory(null); setState(null); setErrorsState({}); }} className="text-xs text-ops-textDim hover:text-ops-accent">Change category</button>
            )}
          </div>

          {errors._general && <div role="alert" className="rounded-md border border-ops-danger/40 bg-ops-danger/10 p-3 text-sm text-ops-danger">{errors._general}</div>}
          {Object.keys(errors).some((k) => k !== '_general') && (
            <p className="text-xs text-ops-danger">Some fields need attention — they are marked below. Everything you entered has been kept.</p>
          )}

          <Form form={state} onChange={setState} errors={errors} setErrors={setErrors} roles={catalog.roles} knownPlaces={knownPlaces} />

          {mod.ready && (
            <div className="sticky bottom-0 flex flex-wrap items-center justify-end gap-3 border-t border-ops-border bg-ops-bg/90 py-3 backdrop-blur">
              <Link to={isEdit ? `/missions/${savedId}` : '/missions'} className="rounded-md border border-ops-border px-4 py-2 text-xs text-ops-textDim">Cancel</Link>
              <button type="button" disabled={saving} onClick={() => void run(false)}
                      className="rounded-md border border-ops-accent px-4 py-2 text-xs font-semibold text-ops-accent disabled:opacity-50">{saving ? 'Saving…' : 'Save draft'}</button>
              <button type="button" disabled={saving} onClick={() => void run(true)}
                      className="rounded-md bg-ops-accent px-4 py-2 text-xs font-semibold text-ops-bg disabled:opacity-50">{saving ? 'Working…' : 'Save & submit for approval'}</button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
