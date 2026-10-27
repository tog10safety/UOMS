import { FormEvent, useState } from 'react';

import { extractApiError, fromDatetimeLocal, parseCoordinateLines, toDatetimeLocal } from '@/utils/errors';

import {
  CheckboxField, FieldWrapper, FormActions, SearchField, SelectField, TextAreaField, TextField, inputClass,
} from './FormFields';
import Modal from './Modal';
import type { SearchableOption } from './SearchableSelect';

export type FieldType =
  | 'text' | 'textarea' | 'number' | 'date' | 'datetime' | 'email' | 'password' | 'color'
  | 'select' | 'search' | 'multiselect' | 'checkbox' | 'latlng' | 'coords' | 'file';

export interface FieldDef {
  /** Key in the form state (and in the API payload unless `payloadKey` is set). */
  name: string;
  label: string;
  type: FieldType;
  required?: boolean;
  options?: SearchableOption[];
  placeholder?: string;
  help?: string;
  /** 2 = full width inside the 2-column form grid. */
  span?: 1 | 2;
  step?: string;
  defaultValue?: unknown;
  createOnly?: boolean;
  editOnly?: boolean;
  /** API key to send instead of `name` (e.g. `location_input` for geometry). */
  payloadKey?: string;
  /** Derive the form value from an existing record (needed for geometry fields etc.). */
  getInitial?: (record: any) => unknown;
}


export type FormValues = Record<string, any>;

export function defaultFor(field: FieldDef): unknown {
  if (field.defaultValue !== undefined) return field.defaultValue;
  switch (field.type) {
    case 'search': return null;
    case 'multiselect': return [];
    case 'checkbox': return false;
    case 'latlng': return { lat: '', lng: '' };
    case 'file': return null;
    default: return '';
  }
}

export function initialFromRecord(field: FieldDef, record: any): unknown {
  if (field.getInitial) return field.getInitial(record);
  const raw = record?.[field.name];
  if (raw === undefined || raw === null) return defaultFor(field);
  switch (field.type) {
    case 'datetime': return toDatetimeLocal(raw);
    case 'number': return String(raw);
    case 'date': return String(raw).slice(0, 10);
    case 'multiselect': return Array.isArray(raw) ? raw : [];
    case 'file': return null;
    default: return raw;
  }
}

export function buildPayload(fields: FieldDef[], values: FormValues, mode: 'create' | 'edit') {
  const payload: Record<string, any> = {};

  for (const field of fields) {
    if ((field.createOnly && mode === 'edit') || (field.editOnly && mode === 'create')) continue;
    const value = values[field.name];
    const key = field.payloadKey ?? field.name;

    switch (field.type) {
      case 'number':
        if (value === '' || value == null) {
          if (!field.required) payload[key] = null;
        } else payload[key] = Number(value);
        break;
      case 'date':
        payload[key] = value || null;
        break;
      case 'datetime':
        payload[key] = fromDatetimeLocal(value);
        break;
      case 'search':
        payload[key] = value || null;
        break;
      case 'select':
        if (value !== '') payload[key] = value;
        break;
      case 'password':
        if (value) payload[key] = value;
        break;
      case 'latlng':
        if (value?.lat !== '' && value?.lng !== '' && value?.lat != null && value?.lng != null) {
          payload[key] = { lat: Number(value.lat), lng: Number(value.lng) };
        }
        break;
      case 'coords': {
        const coords = parseCoordinateLines(value ?? '');
        if (coords.length) payload[key] = coords;
        break;
      }
      case 'file':
        if (value instanceof File) payload[key] = value;
        break;
      default:
        payload[key] = value;
    }
  }
  return payload;
}

export function toFormData(payload: Record<string, any>) {
  const fd = new FormData();
  Object.entries(payload).forEach(([key, value]) => {
    if (value === undefined) return;
    if (value === null) fd.append(key, '');
    else if (value instanceof File) fd.append(key, value);
    else if (Array.isArray(value) && value.every((v) => typeof v === 'string')) value.forEach((v) => fd.append(key, v));
    else if (typeof value === 'object') fd.append(key, JSON.stringify(value));
    else fd.append(key, String(value));
  });
  return fd;
}


const fullWidthTypes: FieldType[] = ['textarea', 'multiselect', 'latlng', 'coords', 'file'];

interface RecordFormModalProps {
  title: string;
  fields: FieldDef[];
  /** Pass the existing record to edit it; omit to create. */
  record?: any | null;
  width?: 'sm' | 'md' | 'lg' | 'xl';
  submitLabel?: string;
  transformPayload?: (payload: Record<string, any>, mode: 'create' | 'edit') => Record<string, any>;
  /** Throw to keep the dialog open and show the error; resolve to close it. */
  onSubmit: (body: any, mode: 'create' | 'edit') => Promise<void>;
  onClose: () => void;
}

export default function RecordFormModal({
  title, fields, record, width = 'md', submitLabel, transformPayload, onSubmit, onClose,
}: RecordFormModalProps) {
  const mode: 'create' | 'edit' = record ? 'edit' : 'create';
  const [values, setValues] = useState<FormValues>(() =>
    mode === 'edit'
      ? Object.fromEntries(fields.filter((f) => !f.createOnly).map((f) => [f.name, initialFromRecord(f, record)]))
      : Object.fromEntries(fields.filter((f) => !f.editOnly).map((f) => [f.name, defaultFor(f)])),
  );
  const [formError, setFormError] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setFormError('');
    try {
      let payload = buildPayload(fields, values, mode);
      if (transformPayload) payload = transformPayload(payload, mode);
      const body = Object.values(payload).some((v) => v instanceof File) ? toFormData(payload) : payload;
      await onSubmit(body, mode);
    } catch (err) {
      setFormError(
        err instanceof Error && !(err as any).response ? err.message : extractApiError(err, 'Unable to save. Please check the required fields.'),
      );
    } finally {
      setIsSaving(false);
    }
  };

  const setValue = (name: string, value: unknown) => setValues((prev) => ({ ...prev, [name]: value }));

  const renderField = (field: FieldDef) => {
    const value = values[field.name];
    const common = { label: field.label, required: field.required, help: field.help };

    switch (field.type) {
      case 'textarea':
        return <TextAreaField {...common} value={value ?? ''} onChange={(v) => setValue(field.name, v)} placeholder={field.placeholder} />;
      case 'select':
        return <SelectField {...common} value={value ?? ''} onChange={(v) => setValue(field.name, v)} options={field.options ?? []} />;
      case 'search':
        return <SearchField {...common} value={value ?? null} onChange={(v) => setValue(field.name, v)} options={field.options ?? []} placeholder={field.placeholder} />;
      case 'checkbox':
        return <CheckboxField label={field.label} help={field.help} checked={!!value} onChange={(v) => setValue(field.name, v)} />;
      case 'multiselect': {
        const selected: string[] = value ?? [];
        return (
          <FieldWrapper {...common}>
            <div className="max-h-32 space-y-1 overflow-y-auto rounded-md border border-ops-border bg-ops-panelLight p-2">
              {(field.options ?? []).length === 0 && <p className="text-xs text-ops-textDim">No options available.</p>}
              {(field.options ?? []).map((o) => (
                <label key={o.value} className="flex cursor-pointer items-center gap-2 text-xs text-ops-text">
                  <input
                    type="checkbox"
                    checked={selected.includes(o.value)}
                    onChange={(e) => setValue(field.name, e.target.checked ? [...selected, o.value] : selected.filter((s) => s !== o.value))}
                    className="rounded border-ops-border"
                  />
                  {o.label}
                </label>
              ))}
            </div>
          </FieldWrapper>
        );
      }
      case 'latlng':
        return (
          <FieldWrapper {...common}>
            <div className="grid grid-cols-2 gap-2">
              <input
                type="number" step="any" min={-90} max={90} placeholder="Latitude" required={field.required}
                value={value?.lat ?? ''} onChange={(e) => setValue(field.name, { ...value, lat: e.target.value })} className={inputClass}
              />
              <input
                type="number" step="any" min={-180} max={180} placeholder="Longitude" required={field.required}
                value={value?.lng ?? ''} onChange={(e) => setValue(field.name, { ...value, lng: e.target.value })} className={inputClass}
              />
            </div>
          </FieldWrapper>
        );
      case 'coords':
        return (
          <FieldWrapper {...common} help={field.help ?? 'One "lat, lng" pair per line.'}>
            <textarea
              rows={5} required={field.required} value={value ?? ''} placeholder={field.placeholder ?? '14.5995, 120.9842\n14.6100, 120.9900'}
              onChange={(e) => setValue(field.name, e.target.value)} className={`${inputClass} font-mono text-xs`}
            />
          </FieldWrapper>
        );
      case 'file':
        return (
          <FieldWrapper {...common}>
            <input
              type="file" accept="image/*"
              onChange={(e) => setValue(field.name, e.target.files?.[0] ?? null)}
              className="block w-full text-xs text-ops-textDim file:mr-3 file:rounded-md file:border file:border-ops-border file:bg-ops-panelLight file:px-3 file:py-1.5 file:text-xs file:text-ops-text"
            />
          </FieldWrapper>
        );
      case 'color':
        return (
          <FieldWrapper {...common}>
            <input type="color" value={value || '#22d3ee'} onChange={(e) => setValue(field.name, e.target.value)} className="h-9 w-full rounded-md border border-ops-border bg-ops-panelLight" />
          </FieldWrapper>
        );
      default:
        return (
          <TextField
            {...common}
            type={field.type === 'datetime' ? 'datetime-local' : field.type}
            step={field.step}
            value={value ?? ''}
            placeholder={field.placeholder}
            onChange={(v) => setValue(field.name, v)}
          />
        );
    }
  };

  const formFields = fields.filter((f) => (mode === 'edit' ? !f.createOnly : !f.editOnly));

  return (
    <Modal title={title} width={width === 'xl' ? 'xl' : width} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          {formFields.map((field) => (
            <div key={field.name} className={field.span === 2 || (field.span === undefined && fullWidthTypes.includes(field.type)) ? 'col-span-2' : ''}>
              {renderField(field)}
            </div>
          ))}
        </div>
        {formError && <p className="text-xs text-ops-danger">{formError}</p>}
        <FormActions onCancel={onClose} isSaving={isSaving} submitLabel={submitLabel} />
      </form>
    </Modal>
  );
}
