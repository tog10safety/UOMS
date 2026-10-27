import { FormEvent, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { unitsApi, missionsApi } from '@/api/endpoints';
import { mrmApi } from '@/api/mrmApi';
import { SearchField, SelectField, TextAreaField, TextField, inputClass } from '@/components/common/FormFields';
import { PercentBar, RiskCell } from '@/components/mrm/MrmBadges';
import { useMrmConfig, useMrmMe } from '@/components/mrm/useMrm';
import { useToast } from '@/contexts/ToastContext';
import type { MissionListItem, Unit } from '@/types';
import type { Hazard, MrmDetail, MrmFormInput, RiskPreview, RiskTier } from '@/types/mrm';
import { extractApiError } from '@/utils/errors';
import { clearError, errorsFromAxios, firstErrorKey, type FieldErrors } from '@/utils/formErrors';
import { MRM_FIELD_ORDER, validateMrmDraft } from '@/utils/mrmValidation';

interface Selected {
  hazard: string;
  activity_code: string;
  description: string;
  mitigations: string;
  before: { rating: string; level: RiskTier };
  after: { rating: string; level: RiskTier; likelihood: number; severity: string };
  overrideOn: boolean;
  override_likelihood: string;
  override_severity: string;
  additional: string;
}

const fromRegistry = (h: Hazard): Selected => ({
  hazard: h.id, activity_code: h.activity_code, description: h.hazard_description, mitigations: h.mitigations,
  before: { rating: h.before_risk_rating, level: h.before_level },
  after: { rating: h.after_risk_rating, level: h.after_level, likelihood: h.after_likelihood, severity: h.after_severity },
  overrideOn: false, override_likelihood: String(h.after_likelihood), override_severity: h.after_severity, additional: '',
});

const fromLine = (l: MrmDetail['hazards'][number]): Selected => ({
  hazard: l.hazard, activity_code: l.activity_code, description: l.hazard_description, mitigations: l.mitigations,
  before: { rating: l.before.rating, level: l.before.level },
  after: { rating: l.registry_after.rating, level: l.registry_after.level, likelihood: l.registry_after.likelihood, severity: l.registry_after.severity },
  overrideOn: !!l.override,
  override_likelihood: String(l.override?.likelihood ?? l.registry_after.likelihood),
  override_severity: l.override?.severity ?? l.registry_after.severity,
  additional: l.additional_mitigations,
});

const toPayloadHazards = (items: Selected[]): MrmFormInput['hazards'] =>
  items.map((s) => ({
    hazard: s.hazard,
    ...(s.overrideOn
      ? { override_likelihood: Number(s.override_likelihood), override_severity: s.override_severity }
      : { override_likelihood: null, override_severity: '' }),
    additional_mitigations: s.additional,
  }));

export default function MrmFormEditor() {
  const { id } = useParams();
  const [query] = useSearchParams();
  const navigate = useNavigate();
  const config = useMrmConfig();
  const me = useMrmMe();
  const { showSuccess } = useToast();
  const isEdit = !!id;

  const [form, setForm] = useState<MrmDetail | null>(null);
  const [loading, setLoading] = useState(isEdit);
  const [loadError, setLoadError] = useState('');
  const [unit, setUnit] = useState<string | null>(null);
  const [units, setUnits] = useState<Unit[]>([]);
  const [missions, setMissions] = useState<MissionListItem[]>([]);
  const [evaluators, setEvaluators] = useState<{ id: string; name: string; unit: string | null }[]>([]);

  const [mission, setMission] = useState<string | null>(query.get('mission'));
  const [activity, setActivity] = useState('');
  const [aircraft, setAircraft] = useState('');
  const [objectives, setObjectives] = useState('');
  const [statement, setStatement] = useState('');
  const [reviewer, setReviewer] = useState<string | null>(null);
  const [imsafe, setImsafe] = useState<Record<string, boolean>>({});
  const [env, setEnv] = useState<Record<string, string>>({ weather: '', lighting: '', workspace: '', operational_tempo: '' });
  const [selected, setSelected] = useState<Selected[]>([]);
  const [tagged, setTagged] = useState<{ user: string; name: string; role: string }[]>([]);

  const [preview, setPreview] = useState<RiskPreview | null>(null);
  const [previewError, setPreviewError] = useState('');
  const [saving, setSaving] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const err = (k: string) => fieldErrors[k];
  const edit = <T,>(setter: (v: T) => void, ...keys: string[]) => (v: T) => { setter(v); setFieldErrors((e) => clearError(e, ...keys, '_general')); };

  const isAdmin = !!me?.is_admin;
  const effectiveUnit = isEdit ? form?.unit ?? null : unit;
  const mode = form?.can.edit ?? (isEdit ? null : 'creator_draft');
  const reviewerLocked = mode === 'creator_submitted' || mode === 'evaluator';

  // ---- load ------------------------------------------------------------------
  useEffect(() => {
    if (!config) return;
    setStatement((s) => s || config.default_mission_statement);
  }, [config]);

  useEffect(() => {
    if (isAdmin) unitsApi.list().then((d) => setUnits(d.results.filter((u) => u.is_active))).catch(() => {});
  }, [isAdmin]);

  useEffect(() => {
    if (!id) return;
    mrmApi.forms.get(id).then((f) => {
      setForm(f);
      setMission(f.mission);
      setActivity(f.activity_mission);
      setAircraft(f.aircraft_vehicle);
      setObjectives(f.safety_objectives);
      setStatement(f.mission_statement);
      setReviewer(f.reviewer?.id ?? null);
      setImsafe(f.imsafe ?? {});
      setEnv({ weather: '', lighting: '', workspace: '', operational_tempo: '', ...(f.environment_data ?? {}) });
      setSelected(f.hazards.map(fromLine));
      setTagged(f.tagged_personnel.map((t) => ({ user: t.user, name: t.name, role: t.role })));
    }).catch((e) => setLoadError(errorsFromAxios(e, 'Unable to load this MRM.')._general ?? 'Unable to load this MRM.')).finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    missionsApi.list({ page_size: 200 }).then((d) => setMissions(d.results)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!me || (isEdit && !form)) return;
    if (!isEdit && isAdmin && !unit) return;
    // Always scope the list to the form's unit: without it an administrator (who has no home unit) got an empty list.
    mrmApi.forms.evaluators(isEdit ? form?.unit : unit).then(setEvaluators).catch(() => setEvaluators([]));
  }, [me, isEdit, form, unit, isAdmin]);

  // default activity name from the chosen mission
  useEffect(() => {
    if (!isEdit && mission && !activity) {
      const m = missions.find((x) => x.id === mission);
      if (m) setActivity(m.name);
    }
  }, [mission, missions, isEdit, activity]);

  // live risk preview
  useEffect(() => {
    if (selected.length === 0) { setPreview(null); return; }
    const timer = setTimeout(() => {
      mrmApi.forms.calculateRisk(toPayloadHazards(selected), isEdit ? undefined : unit)
        .then((p) => { setPreview(p); setPreviewError(''); })
        .catch((e) => { setPreview(null); setPreviewError(extractApiError(e, '')); });
    }, 400);
    return () => clearTimeout(timer);
  }, [selected, unit, isEdit]);

  // ---- save -------------------------------------------------------------------
  const payload = (): Partial<MrmFormInput> => ({
    ...(isEdit ? {} : { unit: isAdmin ? unit : undefined }),
    mission, activity_mission: activity, safety_objectives: objectives, aircraft_vehicle: aircraft,
    mission_statement: statement, imsafe, environment: env,
    ...(reviewerLocked ? {} : { reviewer }),
    hazards: toPayloadHazards(selected),
    tagged_personnel: tagged.map((t) => ({ user: t.user, role: t.role })),
  });

  const showErrors = (errors: FieldErrors) => {
    setFieldErrors(errors);
    const key = firstErrorKey(errors, MRM_FIELD_ORDER);
    if (key) setTimeout(() => document.getElementById(`field-${key}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 0);
  };

  const save = async (andSubmit: boolean) => {
    if (saving) return;                               // a double click can never fire two requests
    const problems = validateMrmDraft({
      activity, objectives, reviewer, evaluatorIds: evaluators.map((e) => e.id), reviewerLocked,
      imsafe, env, hazardCount: selected.length, needsUnit: !isEdit && isAdmin, unit,
    });
    if (Object.keys(problems).length) { showErrors(problems); return; }

    setSaving(true);
    setFieldErrors({});
    try {
      const saved = isEdit
        ? await mrmApi.forms.update(id!, payload())
        : await mrmApi.forms.create(payload() as MrmFormInput);
      if (andSubmit) {
        await mrmApi.forms.submit(saved.id);
        showSuccess(`MRM ${saved.mrm_number} submitted for review.`);
      } else {
        showSuccess(`MRM ${saved.mrm_number} saved.`);
      }
      navigate(`/mrm/${saved.id}`);
    } catch (e) {
      // Everything the user entered (including the evaluator) stays in state; only the messages change.
      showErrors(errorsFromAxios(e, 'Unable to save the MRM.'));
    } finally {
      setSaving(false);
    }
  };

  if (loadError) return <div className="ops-card p-6 text-sm text-ops-danger">{loadError} <Link to="/mrm" className="ml-2 text-ops-accent">← Back</Link></div>;
  if (loading || !config || !me) return <p className="text-sm text-ops-textDim">Loading…</p>;
  if (isEdit && form && !form.can.edit) {
    return (
      <div className="ops-card space-y-2 p-6">
        <p className="text-sm text-ops-text">{form.can.edit_message}</p>
        <Link to={`/mrm/${form.id}`} className="text-xs text-ops-accent hover:underline">← Back to MRM {form.mrm_number}</Link>
      </div>
    );
  }
  if (!isEdit && !me.can_author) {
    return <div className="ops-card p-6 text-sm text-ops-textDim">Your MRM authority does not allow creating forms.</div>;
  }

  const missionOptions = missions
    .filter((m) => !m.mrm || m.id === form?.mission)
    .map((m) => ({ value: m.id, label: m.name, sublabel: m.unit_name ?? undefined }));

  return (
    <form onSubmit={(e: FormEvent) => { e.preventDefault(); void save(false); }} className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link to={isEdit ? `/mrm/${id}` : '/mrm'} className="text-xs text-ops-textDim hover:text-ops-accent">← {isEdit ? `MRM ${form?.mrm_number}` : 'MRM forms'}</Link>
          <h1 className="text-lg font-semibold text-ops-text">{isEdit ? `Edit MRM ${form?.mrm_number}` : 'New MRM form'}</h1>
          {isEdit && <p className="text-xs text-ops-warning">{form?.can.edit_message}</p>}
        </div>
      </div>

      {fieldErrors._general && <div role="alert" className="rounded-md border border-ops-danger/40 bg-ops-danger/10 p-3 text-sm text-ops-danger">{fieldErrors._general}</div>}
      {Object.keys(fieldErrors).filter((k) => k !== '_general').length > 0 && (
        <p className="text-xs text-ops-danger">Some fields need attention — they are marked below. Everything you entered has been kept.</p>
      )}

      {/* 1 — mission basics */}
      <section className="ops-card space-y-3 p-5">
        <p className="ops-label">1 · Mission / activity</p>
        <div className="grid gap-3 md:grid-cols-2">
          {!isEdit && isAdmin && (
            <SearchField label="Unit" required value={unit} onChange={edit(setUnit, 'unit')} error={err('unit')} placeholder="Unit this MRM is for…"
                         options={units.map((u) => ({ value: u.id, label: u.name, sublabel: u.code }))} />
          )}
          <SearchField label="Linked UOMS mission" value={mission} onChange={setMission} options={missionOptions} placeholder="Optional — link to a mission"
                       help="Linking makes this MRM the approval record for that mission." />
          <div id="field-activity_mission"><TextField label="Activity / Mission" required value={activity} onChange={edit(setActivity, 'activity_mission')} error={err('activity_mission')} /></div>
          <TextField label="Aircraft / Vehicle" value={aircraft} onChange={setAircraft} />
          <div className="md:col-span-2">
            <div id="field-safety_objectives"><TextAreaField label="Safety objectives" required rows={3} value={objectives} onChange={edit(setObjectives, 'safety_objectives')} error={err('safety_objectives')} /></div>
          </div>
          <div className="md:col-span-2">
            <TextAreaField label="Mission statement" rows={2} value={statement} onChange={setStatement} />
          </div>
          <div id="field-reviewer">
            <SelectField
              label="Evaluator (reviewer)" required={!reviewerLocked} disabled={reviewerLocked} value={reviewer ?? ''}
              onChange={edit((v: string) => setReviewer(v || null), 'reviewer')}
              options={evaluators.map((e) => ({ value: e.id, label: e.name }))}
              placeholder={evaluators.length ? '— Select an evaluator —' : '— No evaluator available —'}
              error={err('reviewer')}
              help={reviewerLocked ? 'The evaluator can no longer be changed.' : undefined}
            />
          </div>
        </div>
      </section>

      {/* 2 — IMSAFE + environment */}
      <section className="ops-card space-y-4 p-5">
        <p className="ops-label">2 · Crew readiness &amp; environment</p>
        <div id="field-imsafe" className="grid gap-2 md:grid-cols-2">
          {Object.entries(config.imsafe_checklist).map(([key, text]) => (
            <label key={key} className="flex cursor-pointer items-start gap-2 text-sm text-ops-text">
              <input type="checkbox" checked={!!imsafe[key]} onChange={(e) => { setImsafe({ ...imsafe, [key]: e.target.checked }); setFieldErrors((x) => clearError(x, 'imsafe')); }} className="mt-1 rounded border-ops-border" />
              <span><b className="mr-1 text-ops-accent">{key}</b>{text}</span>
            </label>
          ))}
        </div>
        {err('imsafe') && <p role="alert" className="text-xs text-ops-danger">{err('imsafe')}</p>}
        <div id="field-environment" className="grid gap-3 md:grid-cols-2">
          {([['weather', 'Weather'], ['lighting', 'Lighting'], ['workspace', 'Workspace'], ['operational_tempo', 'Operational tempo']] as const).map(([key, label]) => (
            <SelectField key={key} label={label} required value={env[key] ?? ''} error={env[key] ? undefined : err('environment')} onChange={(v) => { setEnv({ ...env, [key]: v }); setFieldErrors((x) => clearError(x, 'environment')); }}
                         options={config.environment_options[key].map((o) => ({ value: o, label: o }))} />
          ))}
        </div>
        {isEdit && !form?.environment_data?.weather && form?.environment && (
          <p className="text-xs text-ops-textDim">Imported record — previous environment text: “{form.environment}”. Choose the options above to replace it.</p>
        )}
      </section>

      {/* 3 — hazards */}
      <section className="ops-card space-y-4 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="ops-label">3 · Hazards &amp; residual risk</p>
          {preview && (
            <div className="flex items-center gap-4 rounded-md border border-ops-border px-3 py-2 text-xs">
              <PercentBar percent={preview.total_percent} />
              <span className="text-ops-textDim">Decision authority: <b className="text-ops-text">{preview.authority_label}</b></span>
            </div>
          )}
        </div>
        {previewError && <p className="text-xs text-ops-danger">{previewError}</p>}
        <div id="field-hazards">{err('hazards') && <p role="alert" className="text-xs text-ops-danger">{err('hazards')}</p>}</div>

        <HazardPicker unit={effectiveUnit} isEdit={isEdit} selectedIds={new Set(selected.map((s) => s.hazard))}
                      onAdd={(h) => setSelected((cur) => [...cur, fromRegistry(h)])} blocked={!isEdit && isAdmin && !unit} />

        {selected.length === 0 ? (
          <p className="rounded-md border border-dashed border-ops-border p-4 text-center text-sm text-ops-textDim">Select at least one hazard from the registry above.</p>
        ) : (
          <div className="space-y-3">
            {selected.map((s, index) => (
              <SelectedHazard
                key={s.hazard} item={s} config={config}
                onChange={(next) => setSelected(selected.map((x, i) => (i === index ? next : x)))}
                onRemove={() => setSelected(selected.filter((_, i) => i !== index))}
              />
            ))}
          </div>
        )}
      </section>

      {/* 4 — personnel */}
      <section className="ops-card space-y-3 p-5">
        <p className="ops-label">4 · Crew &amp; personnel (asked for feedback after the mission)</p>
        <PersonnelPicker unit={effectiveUnit} roles={config.personnel_roles} tagged={tagged} onChange={setTagged} blocked={!isEdit && isAdmin && !unit} />
      </section>

      <div className="sticky bottom-0 flex flex-wrap items-center justify-end gap-3 border-t border-ops-border bg-ops-bg/90 py-3 backdrop-blur">
        <Link to={isEdit ? `/mrm/${id}` : '/mrm'} className="rounded-md border border-ops-border px-4 py-2 text-xs text-ops-textDim">Cancel</Link>
        <button type="submit" disabled={saving} className="rounded-md border border-ops-accent px-4 py-2 text-xs font-semibold text-ops-accent disabled:opacity-50">
          {saving ? 'Saving…' : isEdit ? 'Save changes' : 'Save draft'}
        </button>
        {(!isEdit || form?.can.submit || form?.status === 'draft') && (
          <button type="button" disabled={saving} onClick={() => void save(true)} className="rounded-md bg-ops-accent px-4 py-2 text-xs font-semibold text-ops-bg disabled:opacity-50">
            Save &amp; submit for review
          </button>
        )}
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------

function HazardPicker(props: { unit: string | null; isEdit: boolean; selectedIds: Set<string>; onAdd: (h: Hazard) => void; blocked: boolean }) {
  const [search, setSearch] = useState('');
  const [activity, setActivity] = useState('');
  const [results, setResults] = useState<Hazard[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open || props.blocked) return;
    const timer = setTimeout(() => {
      mrmApi.hazards.pickable({ search, activity_code: activity, unit: props.unit ?? undefined, page_size: 30 })
        .then((d) => setResults(d.results)).catch(() => setResults([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [open, search, activity, props.unit, props.isEdit, props.blocked]);

  if (props.blocked) return <p className="text-xs text-ops-textDim">Choose a unit first to browse its hazard registry.</p>;

  return (
    <div className="space-y-2">
      <button type="button" onClick={() => setOpen(!open)} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-text hover:border-ops-accent">
        {open ? 'Hide hazard registry' : '+ Add hazards from registry'}
      </button>
      {open && (
        <div className="space-y-2 rounded-md border border-ops-border p-3">
          <div className="flex gap-2">
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search hazards…" className={`${inputClass} max-w-xs`} />
            <input value={activity} onChange={(e) => setActivity(e.target.value)} placeholder="Activity code" className={`${inputClass} max-w-[12rem]`} />
          </div>
          <div className="max-h-64 overflow-y-auto">
            {results.length === 0 && <p className="p-3 text-center text-xs text-ops-textDim">No hazards found. Ask an Evaluator or Safety Officer to add some to the registry.</p>}
            {results.map((h) => {
              const added = props.selectedIds.has(h.id);
              return (
                <div key={h.id} className="flex items-start justify-between gap-3 border-b border-ops-border py-2 last:border-0">
                  <div className="min-w-0">
                    <p className="text-sm text-ops-text">{h.hazard_description}</p>
                    <p className="text-[11px] text-ops-textDim">{h.activity_code} · {h.unit_code}</p>
                  </div>
                  <div className="flex flex-shrink-0 items-center gap-2">
                    <RiskCell rating={h.before_risk_rating} level={h.before_level} />
                    <span className="text-ops-textDim">→</span>
                    <RiskCell rating={h.after_risk_rating} level={h.after_level} />
                    <button type="button" disabled={added} onClick={() => props.onAdd(h)}
                            className="rounded-md bg-ops-accent px-2 py-1 text-xs font-semibold text-ops-bg disabled:opacity-40">{added ? 'Added' : 'Add'}</button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function SelectedHazard({ item, config, onChange, onRemove }: {
  item: Selected; config: NonNullable<ReturnType<typeof useMrmConfig>>; onChange: (s: Selected) => void; onRemove: () => void;
}) {
  const matrix = config.matrix;
  const levelOf = (r: string): RiskTier => (matrix.red.includes(r) ? 'HIGH' : matrix.yellow.includes(r) ? 'MEDIUM' : 'LOW');
  const overrideRating = `${item.override_likelihood}${item.override_severity}`;
  const effective = item.overrideOn ? { rating: overrideRating, level: levelOf(overrideRating) } : item.after;
  const differs = item.overrideOn && overrideRating !== item.after.rating;

  return (
    <div className="rounded-md border border-ops-border p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-ops-text">{item.description}</p>
          <p className="text-[11px] text-ops-textDim">{item.activity_code}</p>
        </div>
        <div className="flex flex-shrink-0 items-center gap-2 text-xs">
          <span className="text-ops-textDim">Before</span><RiskCell rating={item.before.rating} level={item.before.level} />
          <span className="text-ops-textDim">Residual</span><RiskCell rating={effective.rating} level={effective.level} />
          <button type="button" onClick={onRemove} className="ml-2 text-ops-danger hover:underline">Remove</button>
        </div>
      </div>
      <ul className="mt-2 list-disc pl-5 text-xs text-ops-textDim">
        {item.mitigations.split('\n').filter(Boolean).map((m, i) => <li key={i}>{m}</li>)}
      </ul>
      <label className="mt-2 flex items-center gap-2 text-xs text-ops-text">
        <input type="checkbox" checked={item.overrideOn} onChange={(e) => onChange({ ...item, overrideOn: e.target.checked })} className="rounded border-ops-border" />
        Override residual risk for this mission (registry value: {item.after.rating})
      </label>
      {item.overrideOn && (
        <div className="mt-2 grid gap-3 md:grid-cols-3">
          <SelectField label="Likelihood" required value={item.override_likelihood} onChange={(v) => onChange({ ...item, override_likelihood: v })}
                       options={Object.entries(config.likelihoods).sort((a, b) => Number(b[0]) - Number(a[0])).map(([k, v]) => ({ value: k, label: `${k} — ${v}` }))} />
          <SelectField label="Severity" required value={item.override_severity} onChange={(v) => onChange({ ...item, override_severity: v })}
                       options={Object.entries(config.severities).map(([k, v]) => ({ value: k, label: `${k} — ${v}` }))} />
          <div className="md:col-span-3">
            <TextAreaField label={differs ? 'Justification / additional mitigations (required)' : 'Additional mitigations'} rows={2} required={differs}
                           value={item.additional} onChange={(v) => onChange({ ...item, additional: v })}
                           help={differs ? 'Explain why this mission’s residual risk differs from the registry rating.' : undefined} />
          </div>
        </div>
      )}
      {!item.overrideOn && (
        <div className="mt-2">
          <TextField label="Additional mitigations for this mission (optional)" value={item.additional} onChange={(v) => onChange({ ...item, additional: v })} />
        </div>
      )}
    </div>
  );
}

function PersonnelPicker(props: {
  unit: string | null; roles: string[]; tagged: { user: string; name: string; role: string }[];
  onChange: (t: { user: string; name: string; role: string }[]) => void; blocked: boolean;
}) {
  const [q, setQ] = useState('');
  const [results, setResults] = useState<{ id: string; name: string; username: string; service_number: string }[]>([]);
  const [role, setRole] = useState(props.roles[0] ?? 'Crew Member');
  const taken = useMemo(() => new Set(props.tagged.map((t) => t.user)), [props.tagged]);

  useEffect(() => {
    if (props.blocked || q.trim().length < 2) { setResults([]); return; }
    const timer = setTimeout(() => {
      mrmApi.forms.people(q.trim(), props.unit).then(setResults).catch(() => setResults([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [q, props.unit, props.blocked]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search your unit’s personnel by name or service number…" className={`${inputClass} max-w-sm`} />
        <select value={role} onChange={(e) => setRole(e.target.value)} className={`${inputClass} max-w-[10rem]`}>
          {props.roles.map((r) => <option key={r}>{r}</option>)}
        </select>
      </div>
      {results.length > 0 && (
        <div className="rounded-md border border-ops-border">
          {results.filter((r) => !taken.has(r.id)).map((r) => (
            <button type="button" key={r.id} onClick={() => { props.onChange([...props.tagged, { user: r.id, name: r.name, role }]); setQ(''); setResults([]); }}
                    className="flex w-full items-center justify-between border-b border-ops-border px-3 py-2 text-left text-sm last:border-0 hover:bg-ops-panelLight">
              <span className="text-ops-text">{r.name}</span><span className="text-xs text-ops-textDim">{r.service_number || r.username}</span>
            </button>
          ))}
        </div>
      )}
      {props.tagged.length === 0 ? (
        <p className="text-xs text-ops-textDim">No one tagged yet. Tagged people can give feedback once the MRM is approved.</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {props.tagged.map((t) => (
            <span key={t.user} className="flex items-center gap-2 rounded-full border border-ops-border px-3 py-1 text-xs text-ops-text">
              {t.name} <i className="text-ops-textDim">· {t.role}</i>
              <button type="button" onClick={() => props.onChange(props.tagged.filter((x) => x.user !== t.user))} className="text-ops-danger">✕</button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
