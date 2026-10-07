/**
 * Where the map pictures come from. Pick a provider and give it a key; no code change needed.
 *
 *   NEXT_PUBLIC_MAP_PROVIDER = osm (default, free, for trying things out) | maptiler | mapbox
 *   NEXT_PUBLIC_MAP_API_KEY  = the provider's key (map keys are public by design: restrict them to your website in the provider's dashboard)
 *   NEXT_PUBLIC_MAP_TILE_URL = optional: any other tile service, overrides the choice above
 */
export type MapSource = { url: string; attribution: string; provider: string; note?: string };

const OSM = { url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', attribution: '&copy; OpenStreetMap contributors' };

export function mapSource(env: { provider?: string; key?: string; tileUrl?: string; attribution?: string } = {
  provider: process.env.NEXT_PUBLIC_MAP_PROVIDER, key: process.env.NEXT_PUBLIC_MAP_API_KEY, tileUrl: process.env.NEXT_PUBLIC_MAP_TILE_URL, attribution: process.env.NEXT_PUBLIC_MAP_ATTRIBUTION,
}): MapSource {
  const custom = (env.tileUrl ?? '').trim();
  if (custom) return { url: custom, attribution: env.attribution?.trim() || '&copy; OpenStreetMap contributors', provider: 'custom' };

  const provider = (env.provider ?? 'osm').trim().toLowerCase() || 'osm';
  const key = (env.key ?? '').trim();
  if (provider === 'maptiler' && key) {
    return { url: `https://api.maptiler.com/maps/streets-v2/256/{z}/{x}/{y}.png?key=${encodeURIComponent(key)}`, attribution: '&copy; MapTiler &copy; OpenStreetMap contributors', provider: 'maptiler' };
  }
  if (provider === 'mapbox' && key) {
    return { url: `https://api.mapbox.com/styles/v1/mapbox/streets-v12/tiles/256/{z}/{x}/{y}@2x?access_token=${encodeURIComponent(key)}`, attribution: '&copy; Mapbox &copy; OpenStreetMap contributors', provider: 'mapbox' };
  }
  if ((provider === 'maptiler' || provider === 'mapbox') && !key) {
    return { ...OSM, provider: 'osm', note: `${provider} was chosen but NEXT_PUBLIC_MAP_API_KEY is empty, so the free OpenStreetMap tiles are used.` };
  }
  return { ...OSM, provider: 'osm' };
}
