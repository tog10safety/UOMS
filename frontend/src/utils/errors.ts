/**
 * Flattens a DRF error response (field errors, non_field_errors, or `detail`)
 * into a single human-readable string.
 */
export function extractApiError(err: unknown, fallback = 'Unable to complete the request.'): string {
  const data = (err as { response?: { data?: unknown } })?.response?.data;
  if (!data) return fallback;
  if (typeof data === 'string') return data;

  const flatten = (value: unknown, prefix = ''): string[] => {
    if (value == null) return [];
    if (typeof value === 'string') return [prefix ? `${prefix}: ${value}` : value];
    if (Array.isArray(value)) return value.flatMap((v) => flatten(v, prefix));
    if (typeof value === 'object') {
      return Object.entries(value as Record<string, unknown>).flatMap(([key, v]) =>
        flatten(v, key === 'detail' || key === 'non_field_errors' ? '' : key.replace(/_/g, ' ')),
      );
    }
    return [String(value)];
  };

  const messages = flatten(data);
  return messages.length ? messages.join(' ') : fallback;
}

// datetime-local inputs need "YYYY-MM-DDTHH:mm" with no timezone suffix.
export function toDatetimeLocal(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function fromDatetimeLocal(value: string): string | null {
  return value ? new Date(value).toISOString() : null;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

export function parseCoordinateLines(text: string): { lat: number; lng: number }[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [lat, lng] = line.split(/[,\s]+/).map(Number);
      if (Number.isNaN(lat) || Number.isNaN(lng)) {
        throw new Error(`Invalid coordinate "${line}" — use one "lat, lng" pair per line.`);
      }
      return { lat, lng };
    });
}

export function coordinatesToLines(coords: { lat: number; lng: number }[] | null | undefined): string {
  return (coords ?? []).map((c) => `${c.lat}, ${c.lng}`).join('\n');
}
