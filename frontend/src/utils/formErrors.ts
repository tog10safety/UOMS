/**
 * Turns a DRF error response into { fieldPath: message }, so each message can be shown beside its field.
 * Handles {field: ["msg"]}, {field: "msg"}, nested objects, non_field_errors/detail, and plain strings.
 */
export type FieldErrors = Record<string, string>;

const GENERAL_KEYS = new Set(['detail', 'non_field_errors', '']);

export function flattenApiErrors(data: unknown, prefix = ''): FieldErrors {
  const out: FieldErrors = {};
  const add = (key: string, message: string) => {
    const k = GENERAL_KEYS.has(key) ? '_general' : key;
    out[k] = out[k] ? `${out[k]} ${message}` : message;
  };

  const walk = (value: unknown, key: string) => {
    if (value == null) return;
    if (typeof value === 'string') add(key, value);
    else if (Array.isArray(value)) {
      value.forEach((item) => (typeof item === 'string' ? add(key, item) : walk(item, key)));
    } else if (typeof value === 'object') {
      Object.entries(value as Record<string, unknown>).forEach(([k, v]) => {
        if (GENERAL_KEYS.has(k) && !key) walk(v, '');
        else walk(v, key && !GENERAL_KEYS.has(k) ? `${key}.${k}` : key || k);
      });
    } else add(key, String(value));
  };

  walk(data, prefix);
  return out;
}

export function errorsFromAxios(err: unknown, fallback = 'Something went wrong. Please try again.'): FieldErrors {
  const data = (err as { response?: { data?: unknown; status?: number } })?.response?.data;
  if (data && typeof data === 'object') {
    const flat = flattenApiErrors(data);
    if (Object.keys(flat).length) return flat;
  }
  if (typeof data === 'string' && data.trim()) return { _general: data };
  return { _general: fallback };
}

/** First key in `order` that has an error — used to scroll/focus the first problem. */
export function firstErrorKey(errors: FieldErrors, order: string[] = []): string | undefined {
  const keys = Object.keys(errors);
  return order.find((k) => errors[k]) ?? keys.find((k) => k !== '_general') ?? (errors._general ? '_general' : undefined);
}

/** Drop one field's error as soon as the user edits it (keeps the others visible). */
export function clearError(errors: FieldErrors, ...keys: string[]): FieldErrors {
  if (!keys.some((k) => k in errors)) return errors;
  const next = { ...errors };
  keys.forEach((k) => delete next[k]);
  return next;
}
