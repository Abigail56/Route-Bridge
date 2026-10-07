'use client';

import { useEffect, useRef } from 'react';
import type { Map as LeafletMap, LayerGroup, Marker } from 'leaflet';
import 'leaflet/dist/leaflet.css';

export type MapPin = {
  id: string;
  lat: number;
  lng: number;
  /** driver = moving rider, driver-stale = last known position, waiting = order with no rider yet, dropoff = where a rider is heading */
  kind: 'driver' | 'driver-stale' | 'waiting' | 'dropoff';
  label: string;
  detail?: string;
  initials?: string;
};

import { mapSource } from '../lib/map-source';

// The provider (free OpenStreetMap, MapTiler or Mapbox) is chosen in the settings, not in code. See lib/map-source.ts and the README.
const SOURCE = mapSource();
if (SOURCE.note && typeof window !== 'undefined') console.warn(SOURCE.note);
const TILES = SOURCE.url;
const ATTRIBUTION = SOURCE.attribution;
const LAGOS: [number, number] = [6.5244, 3.3792];

function iconHtml(pin: MapPin, selected: boolean): string {
  const ring = selected ? ' rb-pin-selected' : '';
  if (pin.kind === 'waiting') return `<span class="rb-pin rb-pin-waiting${ring}"></span>`;
  if (pin.kind === 'dropoff') return `<span class="rb-pin rb-pin-dropoff${ring}">&#8962;</span>`;
  const text = (pin.initials ?? '').slice(0, 2).toUpperCase().replace(/[<>&]/g, '');
  return `<span class="rb-pin rb-pin-${pin.kind}${ring}">${text}</span>`;
}

/** A live map. Pins can move between updates; the view only re-fits when the SET of pins changes, so it never jumps while you watch. */
export function LiveMap({ pins, height = 440, selectedId, onSelect, emptyText }: { pins: MapPin[]; height?: number; selectedId?: string | null; onSelect?: (id: string) => void; emptyText?: string }) {
  const host = useRef<HTMLDivElement | null>(null);
  const map = useRef<LeafletMap | null>(null);
  const layer = useRef<LayerGroup | null>(null);
  const markers = useRef<Map<string, Marker>>(new Map());
  const fitted = useRef('');
  const leaflet = useRef<typeof import('leaflet') | null>(null);
  const latest = useRef({ pins, selectedId, onSelect });
  latest.current = { pins, selectedId, onSelect };

  function draw() {
    const L = leaflet.current;
    if (!L || !map.current || !layer.current) return;
    const { pins: current, selectedId: chosen, onSelect: select } = latest.current;
    const seen = new Set<string>();
    for (const pin of current) {
      seen.add(pin.id);
      const icon = L.divIcon({ className: 'rb-pin-wrap', html: iconHtml(pin, pin.id === chosen), iconSize: [38, 38], iconAnchor: [19, 19] });
      let marker = markers.current.get(pin.id);
      if (!marker) {
        marker = L.marker([pin.lat, pin.lng], { icon, riseOnHover: true }).addTo(layer.current);
        markers.current.set(pin.id, marker);
      } else {
        marker.setLatLng([pin.lat, pin.lng]);
        marker.setIcon(icon);
      }
      const box = document.createElement('div');
      const title = document.createElement('b');
      title.textContent = pin.label;
      box.appendChild(title);
      if (pin.detail) {
        const line = document.createElement('div');
        line.textContent = pin.detail;
        box.appendChild(line);
      }
      marker.bindPopup(box);
      marker.off('click');
      marker.on('click', () => select?.(pin.id));
    }
    for (const [id, marker] of Array.from(markers.current.entries())) {
      if (!seen.has(id)) { layer.current.removeLayer(marker); markers.current.delete(id); }
    }
    const signature = current.map((pin) => pin.id).sort().join('|');
    if (signature !== fitted.current && current.length) {
      fitted.current = signature;
      const points = current.map((pin) => [pin.lat, pin.lng] as [number, number]);
      if (points.length === 1) map.current.setView(points[0], 14);
      else map.current.fitBounds(points, { padding: [48, 48], maxZoom: 15 });
    }
  }

  useEffect(() => {
    let cancelled = false;
    const pinsOnMap = markers.current;
    (async () => {
      const L = await import('leaflet');
      if (cancelled || !host.current || map.current) return;
      leaflet.current = L;
      map.current = L.map(host.current, { zoomControl: true, attributionControl: true }).setView(LAGOS, 11);
      L.tileLayer(TILES, { attribution: ATTRIBUTION, maxZoom: 19 }).addTo(map.current);
      layer.current = L.layerGroup().addTo(map.current);
      draw();
      setTimeout(() => map.current?.invalidateSize(), 150);
    })();
    return () => { cancelled = true; map.current?.remove(); map.current = null; layer.current = null; pinsOnMap.clear(); fitted.current = ''; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { draw(); });

  useEffect(() => {
    const chosen = selectedId ? markers.current.get(selectedId) : null;
    if (chosen && map.current) { map.current.panTo(chosen.getLatLng()); chosen.openPopup(); }
  }, [selectedId]);

  return <div className="live-map" style={{ height }}>
    <div ref={host} className="live-map-canvas" role="application" aria-label="Live map of drivers and deliveries" />
    {!pins.length && <div className="live-map-empty"><b>{emptyText ?? 'Nothing to show on the map yet.'}</b></div>}
  </div>;
}
