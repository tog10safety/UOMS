import 'ol/ol.css';

import { Feature, Map, View } from 'ol';
import { LineString, Point, Polygon } from 'ol/geom';
import TileLayer from 'ol/layer/Tile';
import VectorLayer from 'ol/layer/Vector';
import { fromLonLat } from 'ol/proj';
import OSM from 'ol/source/OSM';
import VectorSource from 'ol/source/Vector';
import { Circle as CircleStyle, Fill, Stroke, Style, Text } from 'ol/style';
import { useEffect, useRef } from 'react';

import type { OperationalOverlay } from '@/types';

interface GisMapProps {
  overlay: OperationalOverlay;
  visibleLayers: Set<string>;
  height?: string;
}

const HAZARD_COLOR: Record<string, string> = { LOW: '#f59e0b', MEDIUM: '#f59e0b', HIGH: '#ef4444' };

export default function GisMap({ overlay, visibleLayers, height = '480px' }: GisMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);
  const sourceRef = useRef<VectorSource | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const vectorSource = new VectorSource();
    sourceRef.current = vectorSource;
    const vectorLayer = new VectorLayer({ source: vectorSource });

    const map = new Map({
      target: containerRef.current,
      layers: [new TileLayer({ source: new OSM() }), vectorLayer],
      view: new View({ center: fromLonLat([121.04, 14.68]), zoom: 12 }),
      controls: [],
    });

    mapRef.current = map;

    return () => {
      map.setTarget(undefined);
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const source = sourceRef.current;
    const map = mapRef.current;
    if (!source || !map) return;

    source.clear();
    const allCoords: [number, number][] = [];

    if (visibleLayers.has('AOR_BOUNDARIES')) {
      overlay.aor_boundaries.forEach((b) => {
        const coords = b.coordinates.map((c) => fromLonLat([c.lng, c.lat]));
        coords.forEach((c) => allCoords.push(c as [number, number]));
        const feature = new Feature({ geometry: new Polygon([coords]) });
        feature.setStyle(new Style({
          stroke: new Stroke({ color: b.color, width: 2 }),
          fill: new Fill({ color: `${b.color}22` }),
          text: new Text({ text: b.name, fill: new Fill({ color: '#e2e8f0' }), font: '11px sans-serif' }),
        }));
        source.addFeature(feature);
      });
    }

    if (visibleLayers.has('ROUTES')) {
      overlay.routes.forEach((r) => {
        const coords = r.coordinates.map((c) => fromLonLat([c.lng, c.lat]));
        coords.forEach((c) => allCoords.push(c as [number, number]));
        const feature = new Feature({ geometry: new LineString(coords) });
        feature.setStyle(new Style({ stroke: new Stroke({ color: '#a78bfa', width: 3, lineDash: [6, 4] }) }));
        source.addFeature(feature);
      });
    }

    if (visibleLayers.has('CHECKPOINTS')) {
      overlay.checkpoints.forEach((c) => addMarker(source, allCoords, c.lat, c.lng, '#f59e0b', c.name, 'triangle'));
    }
    if (visibleLayers.has('LANDING_ZONES')) {
      overlay.landing_zones.forEach((lz) => addMarker(source, allCoords, lz.lat, lz.lng, '#22c55e', lz.name, 'square'));
    }
    if (visibleLayers.has('HAZARDS')) {
      overlay.hazards.forEach((h) =>
        addMarker(source, allCoords, h.lat, h.lng, HAZARD_COLOR[h.severity] ?? '#ef4444', h.name, 'circle'));
    }
    if (visibleLayers.has('VEHICLES')) {
      overlay.vehicles.forEach((v) => addMarker(source, allCoords, v.lat, v.lng, '#22d3ee', v.label, 'circle'));
    }
    if (visibleLayers.has('MISSIONS')) {
      overlay.missions.forEach((m) => addMarker(source, allCoords, m.lat, m.lng, '#f59e0b', m.label, 'circle'));
    }

    if (allCoords.length > 0) {
      const lons = allCoords.map((c) => c[0]);
      const lats = allCoords.map((c) => c[1]);
      const extent: [number, number, number, number] = [
        Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats),
      ];
      map.getView().fit(extent, { padding: [40, 40, 40, 40], maxZoom: 15, duration: 300 });
    }
  }, [overlay, visibleLayers]);

  return <div ref={containerRef} style={{ height, width: '100%' }} />;
}

function addMarker(
  source: VectorSource,
  allCoords: [number, number][],
  lat: number,
  lng: number,
  color: string,
  label: string,
  shape: 'circle' | 'triangle' | 'square',
) {
  const coord = fromLonLat([lng, lat]) as [number, number];
  allCoords.push(coord);
  const feature = new Feature({ geometry: new Point(coord) });
  feature.setStyle(new Style({
    image: new CircleStyle({
      radius: shape === 'circle' ? 6 : 7,
      fill: new Fill({ color }),
      stroke: new Stroke({ color: '#0b1220', width: 2 }),
    }),
    text: new Text({
      text: label, offsetY: -14, fill: new Fill({ color: '#e2e8f0' }),
      font: '10px sans-serif', backgroundFill: new Fill({ color: '#0b1220cc' }), padding: [1, 3, 1, 3],
    }),
  }));
  source.addFeature(feature);
}
