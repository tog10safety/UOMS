import 'ol/ol.css';

import { Feature, Map, View } from 'ol';
import { Point } from 'ol/geom';
import TileLayer from 'ol/layer/Tile';
import VectorLayer from 'ol/layer/Vector';
import { fromLonLat } from 'ol/proj';
import OSM from 'ol/source/OSM';
import VectorSource from 'ol/source/Vector';
import { Circle as CircleStyle, Fill, Stroke, Style } from 'ol/style';
import { useEffect, useRef } from 'react';

import type { MapPoint } from '@/types';

const TYPE_COLOR: Record<MapPoint['type'], string> = {
  vehicle: '#22d3ee',
  mission: '#f59e0b',
};

interface OperationalMapProps {
  points: MapPoint[];
  height?: string;
}

export default function OperationalMap({ points, height = '360px' }: OperationalMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const vectorSource = new VectorSource();
    const vectorLayer = new VectorLayer({ source: vectorSource });

    const map = new Map({
      target: containerRef.current,
      layers: [new TileLayer({ source: new OSM() }), vectorLayer],
      view: new View({ center: fromLonLat([121.0, 14.6]), zoom: 6 }),
      controls: [],
    });

    mapRef.current = map;

    return () => {
      map.setTarget(undefined);
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const vectorLayer = map.getLayers().getArray().find((l) => l instanceof VectorLayer) as
      | VectorLayer<VectorSource>
      | undefined;
    if (!vectorLayer) return;

    const source = vectorLayer.getSource();
    source?.clear();

    points.forEach((point) => {
      const feature = new Feature({ geometry: new Point(fromLonLat([point.lng, point.lat])) });
      feature.setStyle(
        new Style({
          image: new CircleStyle({
            radius: 6,
            fill: new Fill({ color: TYPE_COLOR[point.type] }),
            stroke: new Stroke({ color: '#0b1220', width: 2 }),
          }),
        }),
      );
      feature.set('label', point.label);
      source?.addFeature(feature);
    });

    if (points.length > 0) {
      const extent = source!.getExtent();
      map.getView().fit(extent, { padding: [40, 40, 40, 40], maxZoom: 12, duration: 300 });
    }
  }, [points]);

  return (
    <div className="ops-card overflow-hidden p-0">
      <div className="flex items-center justify-between border-b border-ops-border px-4 py-2">
        <p className="ops-label">Map Overview</p>
        <div className="flex items-center gap-3 text-xs text-ops-textDim">
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-ops-accent" /> Vehicles
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-ops-warning" /> Missions
          </span>
        </div>
      </div>
      <div ref={containerRef} style={{ height, width: '100%' }} />
    </div>
  );
}
