import { describe, expect, it } from 'vitest';
import { mapSource } from './map-source';

describe('map provider', () => {
  it('uses free OpenStreetMap tiles when nothing is configured', () => {
    expect(mapSource({})).toMatchObject({ provider: 'osm', url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png' });
  });

  it('builds a MapTiler address from the key', () => {
    const source = mapSource({ provider: 'MapTiler', key: ' abc123 ' });
    expect(source.provider).toBe('maptiler');
    expect(source.url).toBe('https://api.maptiler.com/maps/streets-v2/256/{z}/{x}/{y}.png?key=abc123');
    expect(source.attribution).toContain('MapTiler');
  });

  it('builds a Mapbox address from the key and keeps the tile placeholders', () => {
    const source = mapSource({ provider: 'mapbox', key: 'pk.test' });
    expect(source.url).toContain('api.mapbox.com/styles/v1/mapbox/streets-v12/tiles/256/{z}/{x}/{y}@2x?access_token=pk.test');
    expect(source.attribution).toContain('Mapbox');
  });

  it('falls back to OpenStreetMap, and says why, when a paid provider has no key', () => {
    const source = mapSource({ provider: 'mapbox', key: '' });
    expect(source.provider).toBe('osm');
    expect(source.note).toContain('NEXT_PUBLIC_MAP_API_KEY');
  });

  it('lets a custom tile address win over everything', () => {
    expect(mapSource({ provider: 'maptiler', key: 'k', tileUrl: 'https://tiles.example.com/{z}/{x}/{y}.png', attribution: 'Example' })).toMatchObject({ provider: 'custom', attribution: 'Example' });
  });

  it('does not let a key break out of the address', () => {
    expect(mapSource({ provider: 'maptiler', key: 'a&b=c' }).url).toContain('key=a%26b%3Dc');
  });
});
