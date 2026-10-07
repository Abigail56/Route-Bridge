'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { friendlyMessage, type ApiClient, type LiveDriver, type LiveTracking as LiveData } from '../lib/api';
import { LiveMap, type MapPin } from './live-map';

const JOB_LABEL: Record<string, string> = { assigned: 'Rider assigned', accepted: 'Heading to pick up', en_route: 'On the way', arrived: 'Arrived at the door' };
const initialsOf = (name: string) => name.split(' ').filter(Boolean).slice(0, 2).map((part) => part[0]).join('');

export function seenText(seconds: number | null): string {
  if (seconds === null) return 'No position yet';
  if (seconds < 90) return 'Live now';
  if (seconds < 3600) return `Last seen ${Math.round(seconds / 60)} min ago`;
  return `Last seen ${Math.round(seconds / 3600)} h ago`;
}

/** Loads live positions and refreshes them while the page is visible. */
export function useLiveTracking(api: ApiClient, tenantId: string, everyMs = 10_000) {
  const [data, setData] = useState<LiveData | null>(null);
  const [error, setError] = useState('');
  const [updated, setUpdated] = useState<number | null>(null);
  const load = useCallback(async () => {
    try { setData(await api.getLiveTracking(tenantId)); setError(''); setUpdated(Date.now()); } catch (exc) { setError(friendlyMessage(exc)); }
  }, [api, tenantId]);
  useEffect(() => {
    load();
    const timer = setInterval(() => { if (document.visibilityState === 'visible') load(); }, everyMs);
    return () => clearInterval(timer);
  }, [load, everyMs]);
  return { data, error, updated, reload: load };
}

export function pinsFor(data: LiveData | null, options: { showWaiting: boolean; onlyOnDelivery: boolean }): MapPin[] {
  if (!data) return [];
  const pins: MapPin[] = [];
  for (const d of data.drivers) {
    if (options.onlyOnDelivery && !d.job) continue;
    if (d.latitude !== null && d.longitude !== null) {
      pins.push({ id: `d-${d.driver_id}`, lat: d.latitude, lng: d.longitude, kind: d.stale ? 'driver-stale' : 'driver', initials: initialsOf(d.name), label: d.name, detail: d.job ? `${JOB_LABEL[d.job.status] ?? d.job.status}${d.job.order_ref ? `, order ${d.job.order_ref}` : ''}${d.job.eta_minutes ? `, about ${d.job.eta_minutes} min away` : ''}` : `${d.status === 'available' ? 'Free' : d.status}. ${seenText(d.last_seen_seconds)}` });
    }
    if (d.job?.dropoff_latitude != null && d.job.dropoff_longitude != null) {
      pins.push({ id: `drop-${d.job.job_id}`, lat: d.job.dropoff_latitude, lng: d.job.dropoff_longitude, kind: 'dropoff', label: `Drop-off ${d.job.order_ref ?? ''}`.trim(), detail: d.job.address_text ?? undefined });
    }
  }
  if (options.showWaiting) for (const w of data.waiting) pins.push({ id: `w-${w.job_id}`, lat: w.latitude, lng: w.longitude, kind: 'waiting', label: `Waiting: ${w.order_ref ?? 'order'}`, detail: 'No rider yet' });
  return pins;
}

function DriverCard({ driver, selected, onSelect }: { driver: LiveDriver; selected: boolean; onSelect: () => void }) {
  const onJob = Boolean(driver.job);
  const tone = driver.status === 'offline' ? 'neutral' : onJob ? 'blue' : 'green';
  return <button className={`driver-card${selected ? ' selected' : ''}`} onClick={onSelect}>
    <span className={`driver-avatar tone-${tone}`}>{initialsOf(driver.name)}</span>
    <span className="driver-card-body">
      <b>{driver.name}</b>
      <span className="driver-card-line">{onJob ? `${JOB_LABEL[driver.job!.status] ?? driver.job!.status} · order ${driver.job!.order_ref ?? ''}` : driver.status === 'offline' ? 'Offline' : 'Free to take a delivery'}</span>
      {driver.job?.address_text && <span className="driver-card-line">{driver.job.address_text}</span>}
      <span className="driver-card-meta">
        {driver.job?.eta_minutes ? <span className="eta-pill">About {driver.job.eta_minutes} min away</span> : null}
        <span className={driver.latitude === null ? 'seen seen-none' : driver.stale ? 'seen seen-stale' : 'seen seen-live'}><i />{seenText(driver.last_seen_seconds)}</span>
      </span>
    </span>
  </button>;
}

/** The dispatcher's live map: every driver, who is on a delivery, how far they are, and orders still waiting. */
export function LiveTracking({ api, tenantId }: { api: ApiClient; tenantId: string }) {
  const { data, error, updated, reload } = useLiveTracking(api, tenantId);
  const [onlyOnDelivery, setOnlyOnDelivery] = useState(false);
  const [showWaiting, setShowWaiting] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const pins = useMemo(() => pinsFor(data, { showWaiting, onlyOnDelivery }), [data, showWaiting, onlyOnDelivery]);
  const drivers = (data?.drivers ?? []).filter((d) => !onlyOnDelivery || d.job);
  const onDelivery = (data?.drivers ?? []).filter((d) => d.job).length;
  const noPosition = (data?.drivers ?? []).filter((d) => d.latitude === null).length;

  return <section aria-label="Live tracking">
    <div className="tracking-toolbar">
      <div className="segmented">
        <button className={!onlyOnDelivery ? 'selected' : ''} onClick={() => setOnlyOnDelivery(false)}>All drivers</button>
        <button className={onlyOnDelivery ? 'selected' : ''} onClick={() => setOnlyOnDelivery(true)}>On delivery ({onDelivery})</button>
      </div>
      <label className="check"><input type="checkbox" checked={showWaiting} onChange={(event) => setShowWaiting(event.target.checked)} /> Show orders waiting for a rider</label>
      <span className="tracking-updated">{updated ? `Updated ${new Date(updated).toLocaleTimeString()}` : 'Loading…'} <button className="link-button" onClick={reload}>Refresh</button></span>
    </div>
    {error && <p role="alert" className="low-confidence">{error}</p>}
    <div className="tracking-grid">
      <div className="card tracking-map-card">
        <LiveMap pins={pins} height={560} selectedId={selected} onSelect={setSelected} emptyText={data && !data.drivers.some((d) => d.latitude !== null) ? 'No driver has shared a position yet. Ask riders to open the driver app and allow location.' : 'Nothing to show for this filter.'} />
        <div className="map-legend"><span><i className="lg lg-driver" />Rider, live</span><span><i className="lg lg-stale" />Rider, last known</span><span><i className="lg lg-drop" />Drop-off</span><span><i className="lg lg-wait" />Waiting for a rider</span></div>
      </div>
      <div className="tracking-side">
        <h3>{onlyOnDelivery ? 'Riders on a delivery' : 'All riders'}</h3>
        {!drivers.length && <p className="muted">{data ? (onlyOnDelivery ? 'Nobody is out on a delivery right now.' : 'No drivers yet. Add them under Drivers.') : 'Loading…'}</p>}
        <div className="driver-list">{drivers.map((d) => <DriverCard key={d.driver_id} driver={d} selected={selected === `d-${d.driver_id}`} onSelect={() => setSelected(`d-${d.driver_id}`)} />)}</div>
        {noPosition > 0 && <p className="tracking-hint">{noPosition} rider{noPosition === 1 ? ' has' : 's have'} not shared a position yet. They appear on the map once they open the driver app and allow location.</p>}
      </div>
    </div>
  </section>;
}

/** A small live map for the dashboard. Click through to the full map. */
export function MiniLiveMap({ api, tenantId, onOpen }: { api: ApiClient; tenantId: string; onOpen: () => void }) {
  const { data } = useLiveTracking(api, tenantId, 15_000);
  const pins = useMemo(() => pinsFor(data, { showWaiting: true, onlyOnDelivery: false }), [data]);
  const onDelivery = (data?.drivers ?? []).filter((d) => d.job).length;
  return <div className="map-card card">
    <div className="map-header"><div><b>Live map</b><small>{onDelivery} rider{onDelivery === 1 ? '' : 's'} out on delivery</small></div><button className="link-button" onClick={onOpen}>Open full map →</button></div>
    <LiveMap pins={pins} height={250} emptyText="No rider positions yet" />
  </div>;
}
