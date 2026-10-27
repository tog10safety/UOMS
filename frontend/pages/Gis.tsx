import { useCallback, useEffect, useMemo, useState } from 'react';

import { gisApi } from '@/api/endpoints';
import GisMap from '@/components/common/GisMap';
import GisManager from '@/components/gis/GisManager';
import type { OperationalOverlay } from '@/types';

const LAYER_ORDER = ['AOR_BOUNDARIES', 'ROUTES', 'CHECKPOINTS', 'LANDING_ZONES', 'HAZARDS', 'MISSIONS', 'VEHICLES'];

export default function Gis() {
  const [overlay, setOverlay] = useState<OperationalOverlay | null>(null);
  const [visibleLayers, setVisibleLayers] = useState<Set<string>>(new Set(LAYER_ORDER));
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  const loadOverlay = useCallback(
    (isInitial: boolean) =>
      gisApi
        .overlay()
        .then((data) => {
          setOverlay(data);
          // Only reset layer visibility on first load so edits don't undo the user's toggles.
          if (isInitial) setVisibleLayers(new Set(data.layers.filter((l) => l.is_visible_by_default).map((l) => l.layer_type)));
          setError('');
        })
        .catch(() => setError('Unable to load operational map data.')),
    [],
  );

  useEffect(() => {
    loadOverlay(true).finally(() => setIsLoading(false));
  }, [loadOverlay]);

  const toggleLayer = (layerType: string) => {
    setVisibleLayers((prev) => {
      const next = new Set(prev);
      if (next.has(layerType)) next.delete(layerType);
      else next.add(layerType);
      return next;
    });
  };

  const layerDefs = useMemo(() => {
    if (!overlay) return [];
    const byType = new Map(overlay.layers.map((l) => [l.layer_type, l]));
    return LAYER_ORDER.filter((t) => byType.has(t)).map((t) => byType.get(t)!);
  }, [overlay]);

  if (isLoading) return <p className="text-sm text-ops-textDim">Loading operational map…</p>;
  if (error || !overlay) return <p className="text-sm text-ops-danger">{error}</p>;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
        <div className="ops-card p-4 lg:col-span-1">
          <p className="ops-label mb-3">Map Layers</p>
          <div className="space-y-2">
            {layerDefs.map((layer) => (
              <label key={layer.layer_type} className="flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={visibleLayers.has(layer.layer_type)}
                  onChange={() => toggleLayer(layer.layer_type)}
                  className="rounded border-ops-border"
                />
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: layer.color }} />
                <span className="text-ops-text">{layer.name}</span>
              </label>
            ))}
          </div>

          <div className="mt-4 space-y-1 border-t border-ops-border pt-3 text-xs text-ops-textDim">
            <p>{overlay.aor_boundaries.length} AOR boundary(ies)</p>
            <p>{overlay.checkpoints.length} checkpoint(s)</p>
            <p>{overlay.landing_zones.length} landing zone(s)</p>
            <p>{overlay.hazards.length} active hazard(s)</p>
            <p>{overlay.routes.length} route(s)</p>
          </div>
        </div>

        <div className="lg:col-span-3">
          <GisMap overlay={overlay} visibleLayers={visibleLayers} height="500px" />
        </div>
      </div>

      {overlay.hazards.length > 0 && visibleLayers.has('HAZARDS') && (
        <div className="ops-card overflow-hidden">
          <p className="border-b border-ops-border px-4 py-3 text-xs font-medium uppercase tracking-wider text-ops-textDim">
            Active Hazards (MGRS)
          </p>
          <table className="w-full text-left text-sm">
            <thead className="bg-ops-panelLight text-xs uppercase tracking-wider text-ops-textDim">
              <tr>
                <th className="px-4 py-2">Name</th>
                <th className="px-4 py-2">Type</th>
                <th className="px-4 py-2">Severity</th>
                <th className="px-4 py-2">MGRS</th>
              </tr>
            </thead>
            <tbody>
              {overlay.hazards.map((h) => (
                <tr key={h.id} className="border-t border-ops-border">
                  <td className="px-4 py-3">{h.name}</td>
                  <td className="px-4 py-3 text-xs text-ops-textDim">{h.hazard_type.replace('_', ' ')}</td>
                  <td className="px-4 py-3 text-xs text-ops-textDim">{h.severity}</td>
                  <td className="px-4 py-3 font-mono text-xs text-ops-accent">{h.mgrs ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="border-t border-ops-border pt-4">
        <p className="ops-label mb-3">Map Data Management</p>
        <GisManager onChanged={() => void loadOverlay(false)} />
      </div>
    </div>
  );
}
