import type { ReactNode } from 'react';

import SearchableSelect, { SearchableOption } from './SearchableSelect';

export const inputClass =
  'w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent disabled:opacity-60';

export function FieldWrapper({ label, required, help, children }: { label: string; required?: boolean; help?: string; children: ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs text-ops-textDim">
        {label}
        {required ? ' *' : ''}
      </label>
      {children}
      {help && <p className="mt-1 text-[10px] text-ops-textDim">{help}</p>}
    </div>
  );
}

export function TextField(props: {
  label: string; value: string; onChange: (v: string) => void;
  type?: string; required?: boolean; placeholder?: string; help?: string; disabled?: boolean; step?: string;
}) {
  return (
    <FieldWrapper label={props.label} required={props.required} help={props.help}>
      <input
        type={props.type ?? 'text'}
        step={props.step}
        required={props.required}
        disabled={props.disabled}
        placeholder={props.placeholder}
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        className={inputClass}
      />
    </FieldWrapper>
  );
}

export function TextAreaField(props: {
  label: string; value: string; onChange: (v: string) => void; rows?: number; required?: boolean; placeholder?: string; help?: string;
}) {
  return (
    <FieldWrapper label={props.label} required={props.required} help={props.help}>
      <textarea
        rows={props.rows ?? 2}
        required={props.required}
        placeholder={props.placeholder}
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        className={inputClass}
      />
    </FieldWrapper>
  );
}

export function SelectField(props: {
  label: string; value: string; onChange: (v: string) => void;
  options: { value: string; label: string }[]; required?: boolean; allowEmpty?: boolean; help?: string;
}) {
  return (
    <FieldWrapper label={props.label} required={props.required} help={props.help}>
      <select
        required={props.required}
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        className={inputClass}
      >
        {(props.allowEmpty ?? !props.required) && <option value="">— Select —</option>}
        {props.options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </FieldWrapper>
  );
}

export function SearchField(props: {
  label: string; value: string | null; onChange: (v: string | null) => void;
  options: SearchableOption[]; required?: boolean; placeholder?: string; help?: string;
}) {
  return (
    <FieldWrapper label={props.label} required={props.required} help={props.help}>
      <SearchableSelect options={props.options} value={props.value} onChange={props.onChange} placeholder={props.placeholder} />
    </FieldWrapper>
  );
}

export function CheckboxField(props: { label: string; checked: boolean; onChange: (v: boolean) => void; help?: string }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 pt-5 text-sm text-ops-text">
      <input type="checkbox" checked={props.checked} onChange={(e) => props.onChange(e.target.checked)} className="rounded border-ops-border" />
      {props.label}
      {props.help && <span className="text-[10px] text-ops-textDim">{props.help}</span>}
    </label>
  );
}

export function FormActions(props: { onCancel: () => void; isSaving: boolean; submitLabel?: string }) {
  return (
    <div className="flex justify-end gap-2 pt-2">
      <button type="button" onClick={props.onCancel} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-textDim">
        Cancel
      </button>
      <button type="submit" disabled={props.isSaving} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg disabled:opacity-50">
        {props.isSaving ? 'Saving…' : props.submitLabel ?? 'Save'}
      </button>
    </div>
  );
}

export const badgeClass = 'rounded-full px-2 py-0.5 text-xs font-medium';
export const activeBadge = (isActive: boolean) =>
  `${badgeClass} ${isActive ? 'bg-ops-success/10 text-ops-success' : 'bg-ops-textDim/10 text-ops-textDim'}`;
