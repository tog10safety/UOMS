import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';

import { mrmApi, saveBlob } from '@/api/mrmApi';
import { unitsApi } from '@/api/endpoints';
import { SearchField } from '@/components/common/FormFields';
import Modal from '@/components/common/Modal';
import type { FieldDef } from '@/components/common/RecordForm';
import ResourceManager, { ColumnDef } from '@/components/common/ResourceManager';
import { RiskCell } from '@/components/mrm/MrmBadges';
import { useMrmConfig, useMrmMe } from '@/components/mrm/useMrm';
import { useToast } from '@/contexts/ToastContext';
import type { Unit } from '@/types';
import type { Hazard, HazardImportResult } from '@/types/mrm';
import { extractApiError } from '@/utils/errors';

const LIKELIHOOD_OPTIONS = (labels: Record<string, string>) =>
  [5, 4, 3, 2, 1].map((n) => ({ value: String(n), label: `${n} — ${labels[String(n)] ?? ''}` }));
const SEVERITY_OPTIONS = (labels: Record<string, string>) =>
  ['A', 'B', 'C', 'D', 'E'].map((s) => ({ value: s, label: `${s} — ${labels[s] ?? ''}` }));

export default function HazardRegistry() {
  const config = useMrmConfig();
  const me = useMrmMe();
  const { showError } = useToast();

  const [units, setUnits] = useState<Unit[]>([]);
  const [activityCodes, setActivityCodes] = useState<string[]>([]);
  const [filters, setFilters] = useState({ activity_code: '', risk_level: '', unit: '' });
  const [importing, setImporting] = useState(false);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    unitsApi.list().then((d) => setUnits(d.results.filter((u) => u.is_active))).catch(() => {});
  }, []);
  useEffect(() => {
    mrmApi.hazards.activityCodes().then(setActivityCodes).catch(() => {});
  }, [refresh]);

  const canWrite = !!me?.can_manage_registry;
  const multiUnit = !!me && (me.is_admin || me.is_safety_officer || me.sees_all_units);

  const load = useCallback((params: Record<string, string | number | boolean>) => mrmApi.hazards.list(params).then((d) => d.results), []);

  const fields: FieldDef[] = useMemo(() => {
    const L = config?.likelihoods ?? {};
    const S = config?.severities ?? {};
    const codeOptions = (activityCodes.length ? activityCodes : config?.activity_codes ?? []).map((c) => ({ value: c, label: c }));
    return [
      ...(multiUnit
        ? ([{ name: 'unit', label: 'Unit', type: 'search', required: true, createOnly: true, span: 2,
              options: units.map((u) => ({ value: u.id, label: u.name, sublabel: u.code })),
              help: 'The unit whose registry this hazard belongs to (cannot be changed later).' }] as FieldDef[])
        : []),
      { name: 'activity_code', label: 'Activity Code', type: 'search', required: true, options: codeOptions, span: 2 },
      { name: 'hazard_description', label: 'Hazard Description', type: 'textarea', required: true },
      { name: 'before_likelihood', label: 'Likelihood — before mitigation', type: 'select', required: true, defaultValue: '3',
        options: LIKELIHOOD_OPTIONS(L), getInitial: (r: Hazard) => String(r.before_likelihood) },
      { name: 'before_severity', label: 'Severity — before mitigation', type: 'select', required: true, defaultValue: 'C', options: SEVERITY_OPTIONS(S) },
      { name: 'mitigations', label: 'Mitigations (one per line)', type: 'textarea', required: true },
      { name: 'after_likelihood', label: 'Likelihood — after mitigation', type: 'select', required: true, defaultValue: '2',
        options: LIKELIHOOD_OPTIONS(L), getInitial: (r: Hazard) => String(r.after_likelihood) },
      { name: 'after_severity', label: 'Severity — after mitigation', type: 'select', required: true, defaultValue: 'D', options: SEVERITY_OPTIONS(S) },
    ];
  }, [config, units, activityCodes, multiUnit]);

  const columns: ColumnDef<Hazard>[] = [
    { header: 'Activity', render: (h) => h.activity_code, className: 'whitespace-nowrap text-xs text-ops-textDim' },
    { header: 'Hazard', render: (h) => <span className="line-clamp-2 max-w-md text-ops-text">{h.hazard_description}</span> },
    { header: 'Before', render: (h) => <RiskCell rating={h.before_risk_rating} level={h.before_level} /> },
    { header: 'After', render: (h) => <RiskCell rating={h.after_risk_rating} level={h.after_level} /> },
    ...(multiUnit ? [{ header: 'Unit', render: (h: Hazard) => h.unit_code, className: 'text-xs' }] : []),
    { header: 'Used', render: (h) => (h.in_use ? 'In MRMs' : '—'), className: 'text-xs text-ops-textDim' },
  ];

  const params: Record<string, string | number | boolean> = {};
  Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v; });

  const exportExcel = async () => {
    try {
      const { blob, filename } = await mrmApi.hazards.export(params);
      saveBlob(blob, filename);
    } catch (err) {
      showError(extractApiError(err, 'Unable to export hazards.'));
    }
  };

  const downloadTemplate = async () => {
    const { blob, filename } = await mrmApi.hazards.template();
    saveBlob(blob, filename);
  };

  const selectClass = 'rounded-md border border-ops-border bg-ops-panelLight px-2 py-1.5 text-xs text-ops-text';

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-ops-text">Hazard Registry</h1>
        <p className="text-sm text-ops-textDim">
          Reusable hazards rated on the official 5×5 risk matrix. MRM forms pick from your unit&apos;s registry and its mother units&apos;.
          {!canWrite && ' You have read-only access.'}
        </p>
      </div>

      <ResourceManager<Hazard>
        noun="hazard"
        addLabel="+ Add Hazard"
        columns={columns}
        fields={fields}
        load={load}
        create={mrmApi.hazards.create}
        update={mrmApi.hazards.update}
        remove={mrmApi.hazards.remove}
        removeVerb="Delete"
        supportsArchive={false}
        canCreate={canWrite}
        canEdit={canWrite}
        canDelete={canWrite}
        canEditRow={(h) => h.can_edit}
        canDeleteRow={(h) => h.can_edit && !h.in_use}
        rowLabel={(h) => `"${h.hazard_description.slice(0, 40)}…"`}
        searchPlaceholder="Search hazards…"
        extraParams={params}
        refreshKey={refresh}
        onChanged={() => setRefresh((r) => r + 1)}
        formWidth="lg"
        toolbar={
          <>
            <select value={filters.activity_code} onChange={(e) => setFilters({ ...filters, activity_code: e.target.value })} className={selectClass}>
              <option value="">All activities</option>
              {activityCodes.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <select value={filters.risk_level} onChange={(e) => setFilters({ ...filters, risk_level: e.target.value })} className={selectClass}>
              <option value="">Any residual risk</option>
              <option value="high">High (red)</option>
              <option value="medium">Medium (yellow)</option>
              <option value="low">Low (green)</option>
            </select>
            {multiUnit && (
              <select value={filters.unit} onChange={(e) => setFilters({ ...filters, unit: e.target.value })} className={selectClass}>
                <option value="">All units</option>
                {units.map((u) => <option key={u.id} value={u.id}>{u.code}</option>)}
              </select>
            )}
            <button onClick={exportExcel} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-textDim hover:text-ops-text">
              Export Excel
            </button>
            {canWrite && (
              <button onClick={() => setImporting(true)} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-textDim hover:text-ops-text">
                Import Excel
              </button>
            )}
          </>
        }
      />

      {importing && (
        <ImportModal
          units={units}
          multiUnit={multiUnit}
          onTemplate={downloadTemplate}
          onClose={() => setImporting(false)}
          onDone={() => setRefresh((r) => r + 1)}
        />
      )}
    </div>
  );
}

function ImportModal(props: { units: Unit[]; multiUnit: boolean; onTemplate: () => void; onClose: () => void; onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [overwrite, setOverwrite] = useState(false);
  const [unit, setUnit] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<HazardImportResult | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError('');
    try {
      const res = await mrmApi.hazards.import(file, { overwrite, unit: unit ?? undefined });
      setResult(res);
      props.onDone();
    } catch (err) {
      const data = (err as { response?: { data?: HazardImportResult } }).response?.data;
      if (data?.errors?.length) setResult(data);
      else setError(extractApiError(err, 'Import failed.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="Import hazards from Excel" width="lg" onClose={props.onClose}>
      <form onSubmit={submit} className="space-y-3">
        <p className="text-xs text-ops-textDim">
          Required columns: Activity Code, Hazard Description, Before Likelihood, Before Severity, Mitigation Strategies, After Likelihood, After Severity.{' '}
          <button type="button" onClick={props.onTemplate} className="text-ops-accent hover:underline">Download template</button>
        </p>
        <input type="file" accept=".xlsx" onChange={(e) => setFile(e.target.files?.[0] ?? null)}
               className="block w-full text-xs text-ops-textDim file:mr-3 file:rounded-md file:border file:border-ops-border file:bg-ops-panelLight file:px-3 file:py-1.5 file:text-xs file:text-ops-text" />
        {props.multiUnit && (
          <SearchField label="Import into unit" value={unit} onChange={setUnit} placeholder="Defaults to your unit"
                       options={props.units.map((u) => ({ value: u.id, label: u.name, sublabel: u.code }))} />
        )}
        <label className="flex items-center gap-2 text-sm text-ops-text">
          <input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} className="rounded border-ops-border" />
          Overwrite hazards that already exist (same activity code and description)
        </label>
        {error && <p className="text-xs text-ops-danger">{error}</p>}
        {result && (
          <div className="space-y-1 rounded-md border border-ops-border p-3 text-xs">
            <p className="text-ops-success">{result.created} created · {result.updated} updated · {result.skipped} skipped</p>
            {result.errors.map((m) => <p key={m} className="text-ops-danger">{m}</p>)}
            {result.skip_reasons.slice(0, 20).map((m) => <p key={m} className="text-ops-textDim">{m}</p>)}
            {result.skip_reasons.length > 20 && <p className="text-ops-textDim">…and {result.skip_reasons.length - 20} more</p>}
          </div>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={props.onClose} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-textDim">Close</button>
          <button type="submit" disabled={!file || busy} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg disabled:opacity-50">
            {busy ? 'Importing…' : 'Import'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
