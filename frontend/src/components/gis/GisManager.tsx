import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';

import {
  aorBoundariesApi, checkpointsApi, gisApi, gisRoutesApi, landingZonesApi, mapHazardsApi, mapLayersApi, personnelApi, unitsApi,
} from '@/api/endpoints';
import { badgeClass, TextField } from '@/components/common/FormFields';
import type { FieldDef } from '@/components/common/RecordForm';
import ResourceManager, { ColumnDef } from '@/components/common/ResourceManager';
import { useAuth } from '@/contexts/AuthContext';
import type {
  AORBoundary, Checkpoint, GisRoute, LandingZone, LatLng, MapHazard, MapLayerDef, PersonnelListItem, Unit,
} from '@/types';
import { coordinatesToLines, extractApiError, formatDateTime } from '@/utils/errors';

type Tab = 'aor' | 'checkpoints' | 'lz' | 'hazards' | 'routes' | 'layers' | 'mgrs';

const TABS: { key: Tab; label: string }[] = [
  { key: 'aor', label: 'AOR Boundaries' },
  { key: 'checkpoints', label: 'Checkpoints' },
  { key: 'lz', label: 'Landing Zones' },
  { key: 'hazards', label: 'Map Hazards' },
  { key: 'routes', label: 'Routes' },
  { key: 'layers', label: 'Map Layers' },
  { key: 'mgrs', label: 'MGRS Converter' },
];

const opts = (values: string[]) => values.map((v) => ({ value: v, label: v.replace(/_/g, ' ') }));

const locationField = (label = 'Location'): FieldDef => ({
  name: 'location', label, type: 'latlng', required: true, payloadKey: 'location_input',
  getInitial: (r: { location: LatLng | null }) => ({ lat: r.location ? String(r.location.lat) : '', lng: r.location ? String(r.location.lng) : '' }),
});

const mgrsColumn = <T extends { location: { mgrs: string | null } | null }>(): ColumnDef<T> => ({
  header: 'MGRS', render: (r) => r.location?.mgrs ?? '—', className: 'font-mono text-xs text-ops-accent',
});

export default function GisManager({ onChanged }: { onChanged: () => void }) {
  const { can } = useAuth();
  const [tab, setTab] = useState<Tab>('aor');
  const [units, setUnits] = useState<Unit[]>([]);
  const [personnel, setPersonnel] = useState<PersonnelListItem[]>([]);

  useEffect(() => {
    unitsApi.list().then((d) => setUnits(d.results.filter((u) => u.is_active))).catch(() => {});
    personnelApi.list({ page_size: 200 }).then((d) => setPersonnel(d.results)).catch(() => {});
  }, []);

  const perms = { canCreate: can('GIS', 'CREATE'), canEdit: can('GIS', 'EDIT'), canDelete: can('GIS', 'DELETE') };
  const unitOptions = useMemo(() => units.map((u) => ({ value: u.id, label: u.name, sublabel: u.code })), [units]);

  const aorFields: FieldDef[] = useMemo(() => [
    { name: 'name', label: 'Name', type: 'text', required: true },
    { name: 'unit', label: 'Unit', type: 'search', options: unitOptions },
    { name: 'color', label: 'Map Colour', type: 'color', defaultValue: '#22d3ee' },
    { name: 'description', label: 'Description', type: 'text' },
    {
      name: 'boundary', label: 'Boundary Polygon', type: 'coords', required: true, payloadKey: 'boundary_input',
      getInitial: (r: AORBoundary) => coordinatesToLines(r.boundary), help: 'One "lat, lng" vertex per line; the ring is closed automatically.',
    },
  ], [unitOptions]);

  const checkpointFields: FieldDef[] = useMemo(() => [
    { name: 'name', label: 'Name', type: 'text', required: true },
    { name: 'checkpoint_type', label: 'Type', type: 'select', required: true, defaultValue: 'OTHER', options: opts(['ENTRY', 'EXIT', 'INSPECTION', 'TRAFFIC_CONTROL', 'OTHER']) },
    locationField(),
    { name: 'unit', label: 'Unit', type: 'search', options: unitOptions },
    { name: 'is_operational', label: 'Operational', type: 'checkbox', defaultValue: true },
    { name: 'remarks', label: 'Remarks', type: 'textarea' },
  ], [unitOptions]);

  const lzFields: FieldDef[] = useMemo(() => [
    { name: 'name', label: 'Name', type: 'text', required: true },
    { name: 'lz_type', label: 'Type', type: 'select', required: true, defaultValue: 'HELICOPTER', options: opts(['HELICOPTER', 'FIXED_WING', 'DROP_ZONE']) },
    { name: 'status', label: 'Status', type: 'select', required: true, defaultValue: 'ACTIVE', options: opts(['ACTIVE', 'INACTIVE', 'UNDER_SURVEY']) },
    { name: 'unit', label: 'Unit', type: 'search', options: unitOptions },
    locationField(),
    { name: 'capacity', label: 'Capacity', type: 'text', placeholder: 'e.g. 2x UH-1' },
    { name: 'surface_type', label: 'Surface Type', type: 'text' },
    { name: 'remarks', label: 'Remarks', type: 'textarea' },
  ], [unitOptions]);

  const hazardFields: FieldDef[] = useMemo(() => [
    { name: 'name', label: 'Name', type: 'text', required: true },
    { name: 'hazard_type', label: 'Type', type: 'select', required: true, defaultValue: 'OTHER', options: opts(['MINEFIELD', 'IED', 'FLOODING', 'LANDSLIDE', 'CIVIL_UNREST', 'OTHER']) },
    { name: 'severity', label: 'Severity', type: 'select', required: true, defaultValue: 'MEDIUM', options: opts(['LOW', 'MEDIUM', 'HIGH']) },
    { name: 'radius_meters', label: 'Affected Radius (m)', type: 'number' },
    locationField(),
    { name: 'reported_by', label: 'Reported By', type: 'search', options: personnel.map((p) => ({ value: p.id, label: p.full_name, sublabel: p.service_number })) },
    { name: 'reported_at', label: 'Reported At', type: 'datetime' },
    { name: 'is_resolved', label: 'Resolved', type: 'checkbox', help: 'Resolved hazards drop off the operational map.' },
    { name: 'description', label: 'Description', type: 'textarea' },
  ], [personnel]);

  const routeFields: FieldDef[] = useMemo(() => [
    { name: 'name', label: 'Name', type: 'text', required: true },
    { name: 'route_type', label: 'Type', type: 'select', required: true, defaultValue: 'OTHER', options: opts(['SUPPLY', 'PATROL', 'EVACUATION', 'OTHER']) },
    { name: 'unit', label: 'Unit', type: 'search', span: 2, options: unitOptions },
    {
      name: 'path', label: 'Route Path', type: 'coords', required: true, payloadKey: 'path_input',
      getInitial: (r: GisRoute) => coordinatesToLines(r.path), help: 'At least two "lat, lng" points, one per line, in travel order.',
    },
    { name: 'description', label: 'Description', type: 'textarea' },
  ], [unitOptions]);

  const layerFields: FieldDef[] = [
    { name: 'name', label: 'Name', type: 'text', required: true },
    { name: 'layer_type', label: 'Layer Type', type: 'select', required: true, defaultValue: 'CUSTOM', options: opts(['AOR_BOUNDARIES', 'CHECKPOINTS', 'LANDING_ZONES', 'HAZARDS', 'ROUTES', 'MISSIONS', 'VEHICLES', 'CUSTOM']), help: 'Each layer type can only exist once.' },
    { name: 'color', label: 'Colour', type: 'color', defaultValue: '#22d3ee' },
    { name: 'is_visible_by_default', label: 'Visible by default', type: 'checkbox', defaultValue: true },
    { name: 'description', label: 'Description', type: 'textarea' },
  ];

  const swatch = (color: string) => <span className="inline-block h-3 w-3 rounded-full align-middle" style={{ backgroundColor: color }} />;

  const loader = <T,>(api: { list: (p?: Record<string, string | number | boolean>) => Promise<{ results: T[] }> }) =>
    // eslint-disable-next-line react-hooks/rules-of-hooks
    useCallback((params: Record<string, string | number | boolean>) => api.list(params).then((d) => d.results), [api]);

  const loadAor = loader<AORBoundary>(aorBoundariesApi);
  const loadCheckpoints = loader<Checkpoint>(checkpointsApi);
  const loadLz = loader<LandingZone>(landingZonesApi);
  const loadHazards = loader<MapHazard>(mapHazardsApi);
  const loadRoutes = loader<GisRoute>(gisRoutesApi);
  const loadLayers = loader<MapLayerDef>(mapLayersApi);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
              tab === t.key ? 'border-ops-accent bg-ops-accent/10 text-ops-accent' : 'border-ops-border text-ops-textDim hover:text-ops-text'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'aor' && (
        <ResourceManager<AORBoundary>
          noun="AOR boundary" columns={[
            { header: 'Name', render: (r) => <>{swatch(r.color)} <span className="ml-1 font-medium text-ops-text">{r.name}</span></> },
            { header: 'Unit', render: (r) => r.unit_name ?? '—' },
            { header: 'Vertices', render: (r) => Math.max((r.boundary?.length ?? 1) - 1, 0), className: 'font-mono text-xs' },
          ]}
          fields={aorFields} load={loadAor} create={aorBoundariesApi.create} update={aorBoundariesApi.update}
          remove={aorBoundariesApi.remove} rowLabel={(r) => r.name} searchPlaceholder="Search boundaries…"
          onChanged={onChanged} {...perms}
        />
      )}

      {tab === 'checkpoints' && (
        <ResourceManager<Checkpoint>
          noun="checkpoint" columns={[
            { header: 'Name', render: (r) => r.name, className: 'font-medium text-ops-text' },
            { header: 'Type', render: (r) => r.checkpoint_type.replace('_', ' ') },
            mgrsColumn<Checkpoint>(),
            { header: 'Unit', render: (r) => r.unit_name ?? '—' },
            { header: 'Operational', render: (r) => <span className={`${badgeClass} ${r.is_operational ? 'bg-ops-success/10 text-ops-success' : 'bg-ops-danger/10 text-ops-danger'}`}>{r.is_operational ? 'Yes' : 'No'}</span> },
          ]}
          fields={checkpointFields} load={loadCheckpoints} create={checkpointsApi.create} update={checkpointsApi.update}
          remove={checkpointsApi.remove} rowLabel={(r) => r.name} searchPlaceholder="Search checkpoints…"
          onChanged={onChanged} {...perms}
        />
      )}

      {tab === 'lz' && (
        <ResourceManager<LandingZone>
          noun="landing zone" columns={[
            { header: 'Name', render: (r) => r.name, className: 'font-medium text-ops-text' },
            { header: 'Type', render: (r) => r.lz_type.replace('_', ' ') },
            { header: 'Status', render: (r) => r.status.replace('_', ' ') },
            mgrsColumn<LandingZone>(),
            { header: 'Capacity', render: (r) => r.capacity || '—', className: 'text-ops-textDim' },
          ]}
          fields={lzFields} load={loadLz} create={landingZonesApi.create} update={landingZonesApi.update}
          remove={landingZonesApi.remove} rowLabel={(r) => r.name} searchPlaceholder="Search landing zones…"
          onChanged={onChanged} {...perms}
        />
      )}

      {tab === 'hazards' && (
        <ResourceManager<MapHazard>
          noun="map hazard" columns={[
            { header: 'Name', render: (r) => r.name, className: 'font-medium text-ops-text' },
            { header: 'Type', render: (r) => r.hazard_type.replace('_', ' ') },
            { header: 'Severity', render: (r) => r.severity },
            mgrsColumn<MapHazard>(),
            { header: 'Reported', render: (r) => (r.reported_by_name ? `${r.reported_by_name} · ${formatDateTime(r.reported_at)}` : '—'), className: 'text-xs text-ops-textDim' },
            { header: 'Resolved', render: (r) => (r.is_resolved ? 'Yes' : 'No') },
          ]}
          fields={hazardFields} load={loadHazards} create={mapHazardsApi.create} update={mapHazardsApi.update}
          remove={mapHazardsApi.remove} rowLabel={(r) => r.name} searchPlaceholder="Search hazards…"
          onChanged={onChanged} {...perms}
        />
      )}

      {tab === 'routes' && (
        <ResourceManager<GisRoute>
          noun="route" columns={[
            { header: 'Name', render: (r) => r.name, className: 'font-medium text-ops-text' },
            { header: 'Type', render: (r) => r.route_type },
            { header: 'Points', render: (r) => r.path?.length ?? 0, className: 'font-mono text-xs' },
            { header: 'Unit', render: (r) => r.unit_name ?? '—' },
          ]}
          fields={routeFields} load={loadRoutes} create={gisRoutesApi.create} update={gisRoutesApi.update}
          remove={gisRoutesApi.remove} rowLabel={(r) => r.name} searchPlaceholder="Search routes…"
          onChanged={onChanged} {...perms}
        />
      )}

      {tab === 'layers' && (
        <ResourceManager<MapLayerDef>
          noun="map layer" columns={[
            { header: 'Name', render: (r) => <>{swatch(r.color)} <span className="ml-1 font-medium text-ops-text">{r.name}</span></> },
            { header: 'Layer Type', render: (r) => r.layer_type.replace('_', ' ') },
            { header: 'Default', render: (r) => (r.is_visible_by_default ? 'Visible' : 'Hidden') },
          ]}
          fields={layerFields} load={loadLayers} create={mapLayersApi.create} update={mapLayersApi.update}
          remove={mapLayersApi.remove} removeVerb="Delete" supportsArchive={false} rowLabel={(r) => r.name}
          onChanged={onChanged} {...perms}
        />
      )}

      {tab === 'mgrs' && <MgrsConverter />}
    </div>
  );
}

function MgrsConverter() {
  const [lat, setLat] = useState('');
  const [lng, setLng] = useState('');
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState('');

  const convert = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setResult(null);
    try {
      const data = await gisApi.convertToMgrs(Number(lat), Number(lng));
      setResult(data.mgrs ?? 'No MGRS grid available for this position.');
    } catch (err) {
      setError(extractApiError(err, 'Unable to convert coordinates.'));
    }
  };

  return (
    <form onSubmit={convert} className="ops-card max-w-xl space-y-3 p-5">
      <p className="ops-label">Latitude / Longitude → MGRS</p>
      <div className="grid grid-cols-2 gap-3">
        <TextField label="Latitude" type="number" step="any" required value={lat} onChange={setLat} />
        <TextField label="Longitude" type="number" step="any" required value={lng} onChange={setLng} />
      </div>
      <button type="submit" className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg">Convert</button>
      {result && <p className="font-mono text-sm text-ops-accent">{result}</p>}
      {error && <p className="text-xs text-ops-danger">{error}</p>}
    </form>
  );
}
