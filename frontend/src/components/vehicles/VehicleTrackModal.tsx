import { FormEvent, useEffect, useState } from 'react';

import { vehiclesApi } from '@/api/endpoints';
import { FormActions, TextField } from '@/components/common/FormFields';
import Modal from '@/components/common/Modal';
import { useToast } from '@/contexts/ToastContext';
import type { VehicleListItem, VehicleLocationUpdate } from '@/types';
import { extractApiError, formatDateTime } from '@/utils/errors';

interface Props {
  vehicle: VehicleListItem;
  canReport: boolean;
  onClose: () => void;
  onReported: () => void;
}

export default function VehicleTrackModal({ vehicle, canReport, onClose, onReported }: Props) {
  const { showSuccess } = useToast();
  const [history, setHistory] = useState<VehicleLocationUpdate[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [form, setForm] = useState({ lat: '', lng: '', speed_kph: '', heading_degrees: '' });
  const [error, setError] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  const loadHistory = () =>
    vehiclesApi
      .locationHistory(vehicle.id)
      .then(setHistory)
      .catch((err) => setError(extractApiError(err, 'Unable to load location history.')))
      .finally(() => setIsLoading(false));

  useEffect(() => {
    loadHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vehicle.id]);

  const handleReport = async (e: FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setError('');
    try {
      await vehiclesApi.reportLocation(vehicle.id, {
        location: { lat: Number(form.lat), lng: Number(form.lng) },
        ...(form.speed_kph ? { speed_kph: Number(form.speed_kph) } : {}),
        ...(form.heading_degrees ? { heading_degrees: Number(form.heading_degrees) } : {}),
      });
      showSuccess(`Location recorded for ${vehicle.plate_number}.`);
      setForm({ lat: '', lng: '', speed_kph: '', heading_degrees: '' });
      await loadHistory();
      onReported();
    } catch (err) {
      setError(extractApiError(err, 'Unable to record location.'));
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Modal title={`Track — ${vehicle.plate_number}`} width="lg" onClose={onClose}>
      {canReport && (
        <form onSubmit={handleReport} className="space-y-3 border-b border-ops-border pb-4">
          <p className="text-xs text-ops-textDim">Report a new position (updates the vehicle's last-known location and track trail).</p>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <TextField label="Latitude" type="number" step="any" required value={form.lat} onChange={(v) => setForm({ ...form, lat: v })} />
            <TextField label="Longitude" type="number" step="any" required value={form.lng} onChange={(v) => setForm({ ...form, lng: v })} />
            <TextField label="Speed (kph)" type="number" step="any" value={form.speed_kph} onChange={(v) => setForm({ ...form, speed_kph: v })} />
            <TextField label="Heading (°)" type="number" step="any" value={form.heading_degrees} onChange={(v) => setForm({ ...form, heading_degrees: v })} />
          </div>
          <FormActions onCancel={onClose} isSaving={isSaving} submitLabel="Record Position" />
        </form>
      )}
      {error && <p className="text-xs text-ops-danger">{error}</p>}

      <p className="ops-label">Location History (latest 200)</p>
      <div className="max-h-64 overflow-y-auto rounded-md border border-ops-border">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-ops-panelLight uppercase tracking-wider text-ops-textDim">
            <tr>
              <th className="px-3 py-2">Recorded</th>
              <th className="px-3 py-2">Latitude</th>
              <th className="px-3 py-2">Longitude</th>
              <th className="px-3 py-2">Speed</th>
              <th className="px-3 py-2">Heading</th>
            </tr>
          </thead>
          <tbody>
            {!isLoading && history.length === 0 && (
              <tr><td colSpan={5} className="px-3 py-4 text-center text-ops-textDim">No location pings recorded yet.</td></tr>
            )}
            {history.map((h) => (
              <tr key={h.id} className="border-t border-ops-border">
                <td className="px-3 py-2 text-ops-textDim">{formatDateTime(h.recorded_at)}</td>
                <td className="px-3 py-2 font-mono">{h.location_display?.lat.toFixed(5) ?? '—'}</td>
                <td className="px-3 py-2 font-mono">{h.location_display?.lng.toFixed(5) ?? '—'}</td>
                <td className="px-3 py-2">{h.speed_kph ? `${h.speed_kph} kph` : '—'}</td>
                <td className="px-3 py-2">{h.heading_degrees ? `${h.heading_degrees}°` : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!canReport && (
        <div className="flex justify-end pt-2">
          <button onClick={onClose} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-textDim">Close</button>
        </div>
      )}
    </Modal>
  );
}
