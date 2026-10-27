import 'ol/ol.css';

import { Feature, Map, View } from 'ol';
import { Point } from 'ol/geom';
import TileLayer from 'ol/layer/Tile';
import VectorLayer from 'ol/layer/Vector';
import { fromLonLat, toLonLat } from 'ol/proj';
import OSM from 'ol/source/OSM';
import VectorSource from 'ol/source/Vector';
import { Circle as CircleStyle, Fill, Stroke, Style } from 'ol/style';
import { useEffect, useRef } from 'react';

interface MapPickerProps {
  lat: number | null;
  lng: number | null;
  onPick: (lat: number, lng: number) => void;
  height?: string;
}

const MARKER = new Style({
  image: new CircleStyle({ radius: 8, fill: new Fill({ color: '#22d3ee' }), stroke: new Stroke({ color: '#0b1220', width: 2 }) }),
});

/** Click-to-select map. A marker shows the current coordinates so a typed MGRS/lat-lng can be verified visually. */
export default function MapPicker({ lat, lng, onPick, height = '260px' }: MapPickerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);
  const sourceRef = useRef<VectorSource | null>(null);
  const onPickRef = useRef(onPick);
  onPickRef.current = onPick;

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const source = new VectorSource();
    sourceRef.current = source;
    const layer = new VectorLayer({ source, style: MARKER });
    const map = new Map({
      target: containerRef.current,
      layers: [new TileLayer({ source: new OSM() }), layer],
      view: new View({ center: fromLonLat([124.65, 8.48]), zoom: 8 }),
    });
    map.on('click', (event) => {
      const [x, y] = toLonLat(event.coordinate);
      onPickRef.current(Number(y.toFixed(6)), Number(x.toFixed(6)));
    });
    mapRef.current = map;
    return () => {
      map.setTarget(undefined);
      mapRef.current = null;
      sourceRef.current = null;
    };
  }, []);

  useEffect(() => {
    const source = sourceRef.current;
    const map = mapRef.current;
    if (!source || !map) return;
    source.clear();
    if (lat != null && lng != null && !Number.isNaN(lat) && !Number.isNaN(lng)) {
      const coord = fromLonLat([lng, lat]);
      source.addFeature(new Feature(new Point(coord)));
      map.getView().animate({ center: coord, zoom: Math.max(map.getView().getZoom() ?? 8, 13), duration: 250 });
    }
  }, [lat, lng]);

  return <div ref={containerRef} style={{ height }} className="w-full overflow-hidden rounded-md border border-ops-border" />;
}
