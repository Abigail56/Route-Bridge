'use client';

import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { API_BASE_URL, readError } from '../../../lib/api';
import { LiveMap } from '../../../components/live-map';
import { alertText, shouldAlert } from '../../../lib/arrival-alert';

type Tracking = {
  reference: string | null; merchant: string | null; status: string; status_label: string; is_final: boolean;
  driver_first_name: string | null;
  rider: { photo?: string | null; latitude: number; longitude: number; updated_seconds_ago: number; eta_minutes: number | null; dropoff: { latitude: number; longitude: number } | null } | null;
  delivery_window: { start: string | null; end: string | null } | null;
  location: { landmark: string | null; plus_code: string | null; confirmed: boolean } | null;
  cod_amount_due: string | null; history: { status: string; label: string; at: string }[];
};

const card = { background: 'var(--white, #fff)', border: '1px solid var(--line, #d9e2e0)', borderRadius: 12, padding: 20, marginBottom: 16 } as const;
const input = { width: '100%', padding: '10px 12px', borderRadius: 8, border: '1px solid var(--line, #d9e2e0)', background: 'transparent', color: 'inherit', font: 'inherit', marginBottom: 10 } as const;
const when = (iso: string | null) => (iso ? new Date(iso.endsWith('Z') || /[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`).toLocaleString('en-NG', { dateStyle: 'medium', timeStyle: 'short' }) : '');

export default function TrackingPage({ params }: { params: { token: string } }) {
  const token = encodeURIComponent(params.token);
  const [data, setData] = useState<Tracking | null>(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [alertsOn, setAlertsOn] = useState(false);
  const lastStatus = useRef<string | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/public/tracking/${token}`);
      if (!response.ok) throw await readError(response);
      const next: Tracking = await response.json();
      // tell the customer when the rider arrives or the parcel is delivered (works while this page stays open, even in another tab)
      if (shouldAlert(lastStatus.current, next.status) && typeof Notification !== 'undefined' && Notification.permission === 'granted') {
        const text = alertText(next.status, next.merchant, next.reference);
        try { new Notification(text.title, { body: text.body, icon: '/logo-tile.png', tag: 'rb-arrival' }); navigator.vibrate?.([200, 100, 200]); } catch { /* some phones only allow alerts from a service worker */ }
      }
      lastStatus.current = next.status;
      setData(next);
      setError('');
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Could not load tracking');
    }
  }, [token]);

  useEffect(() => {
    load();
    if (typeof Notification !== 'undefined' && Notification.permission === 'granted') setAlertsOn(true);
    // a customer who asked for alerts keeps being checked while the tab is hidden (slower, to save their battery)
    let ticks = 0;
    const timer = setInterval(() => { ticks += 1; if (document.visibilityState === 'visible' || (Notification.permission === 'granted' && ticks % 2 === 0)) load(); }, 15000);
    return () => clearInterval(timer);
  }, [load]);

  async function send(path: string, body: unknown, success: string) {
    setBusy(true);
    setMessage('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/public/tracking/${token}/${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      if (!response.ok) throw await readError(response);
      setMessage(success);
      load();
    } catch (exc) {
      setMessage(exc instanceof Error ? exc.message : 'Something went wrong');
    } finally {
      setBusy(false);
    }
  }

  function submitCorrection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body: Record<string, unknown> = {};
    for (const key of ['landmark', 'delivery_notes', 'plus_code']) {
      const value = String(form.get(key) ?? '').trim();
      if (value) body[key] = value;
    }
    const availability = String(form.get('recipient_available') ?? '');
    if (availability) body.recipient_available = availability === 'yes';
    if (!Object.keys(body).length) { setMessage('Add at least one detail to send.'); return; }
    send('correction', body, 'Thanks - your delivery details were updated.');
  }

  if (error) return <main style={{ maxWidth: 520, margin: '12vh auto', padding: 20, textAlign: 'center' }}><h1 style={{ fontSize: 24 }}>Tracking unavailable</h1><p>{error}</p></main>;
  if (!data) return <main style={{ maxWidth: 520, margin: '12vh auto', padding: 20, textAlign: 'center' }}>Loading…</main>;

  return <main style={{ maxWidth: 560, margin: '0 auto', padding: '32px 16px 64px' }}>
    <img src="/logo-tile.png" alt="RouteBridge" width={48} height={48} style={{ borderRadius: 12, display: 'block', marginBottom: 10 }} />
    <p style={{ fontSize: 12, letterSpacing: 1, color: 'var(--muted, #6b7a79)' }}>{data.merchant ?? 'RouteBridge'} · ORDER {data.reference}</p>
    <h1 style={{ fontSize: 32, margin: '4px 0 8px' }}>{data.status_label}</h1>
    {/* eslint-disable-next-line @next/next/no-img-element */}
    {!data.is_final && typeof Notification !== 'undefined' && Notification.permission !== 'denied' && !alertsOn && <p><button type="button" className="button secondary" onClick={async () => { const result = await Notification.requestPermission(); setAlertsOn(result === 'granted'); }}>🔔 Alert me when my rider arrives</button></p>}
    {alertsOn && !data.is_final && <p style={{ fontSize: 14, color: 'var(--muted, #6b7a79)' }}>🔔 We will alert you here when your rider arrives. Keep this page open.</p>}
    {/* eslint-disable-next-line @next/next/no-img-element */}
    {data.driver_first_name && !data.is_final && <p style={{ display: 'flex', alignItems: 'center', gap: 10 }}>{data.rider?.photo && <img src={data.rider.photo} alt={`Photo of ${data.driver_first_name}`} width={48} height={48} style={{ borderRadius: '50%', objectFit: 'cover' }} />}<span>Your driver is <b>{data.driver_first_name}</b>.</span></p>}
    {data.rider && !data.is_final && <section style={card} aria-label="Where your rider is">
      <p style={{ margin: '0 0 10px', fontSize: 18 }}>{data.status === 'arrived' ? <b>Your rider has arrived.</b> : data.rider.eta_minutes ? <><b>{data.driver_first_name ?? 'Your rider'}</b> is about <b>{data.rider.eta_minutes} minute{data.rider.eta_minutes === 1 ? '' : 's'}</b> away.</> : <><b>{data.driver_first_name ?? 'Your rider'}</b> is on the way.</>}</p>
      <LiveMap height={280} pins={[
        { id: 'rider', lat: data.rider.latitude, lng: data.rider.longitude, kind: 'driver', initials: (data.driver_first_name ?? 'R').slice(0, 1), label: data.driver_first_name ?? 'Your rider', detail: 'Updated ' + (data.rider.updated_seconds_ago < 90 ? 'just now' : Math.round(data.rider.updated_seconds_ago / 60) + ' min ago') },
        ...(data.rider.dropoff ? [{ id: 'home', lat: data.rider.dropoff.latitude, lng: data.rider.dropoff.longitude, kind: 'dropoff' as const, label: 'Your delivery address' }] : []),
      ]} />
      <p style={{ margin: '8px 0 0', fontSize: 13, color: 'var(--muted, #6b7a79)' }}>The time is an estimate based on distance and usual city speed. The map refreshes by itself.</p>
    </section>}
    {data.delivery_window && <p>Delivery window: {when(data.delivery_window.start)} – {when(data.delivery_window.end)}</p>}
    {data.cod_amount_due && !data.is_final && <p>Please have <b>₦{Number(data.cod_amount_due).toLocaleString('en-NG')}</b> ready for payment on delivery.</p>}

    <section style={card} aria-label="Progress">
      <b>Progress</b>
      <ol style={{ listStyle: 'none', padding: 0, margin: '12px 0 0' }}>
        {data.history.length === 0 && <li>Order received</li>}
        {data.history.map((item, index) => <li key={index} style={{ padding: '6px 0', display: 'flex', justifyContent: 'space-between', gap: 12 }}><span>{item.label}</span><span style={{ color: 'var(--muted, #6b7a79)', fontSize: 12 }}>{when(item.at)}</span></li>)}
      </ol>
    </section>

    {!data.is_final && <section style={card} aria-label="Delivery details">
      <b>Help us find you</b>
      <p style={{ fontSize: 13, color: 'var(--muted, #6b7a79)' }}>{data.location?.confirmed ? 'Your location is confirmed. You can still add details.' : 'Add a landmark or plus code so the driver can reach you quickly.'}</p>
      <form onSubmit={submitCorrection}>
        <input style={input} name="landmark" placeholder="Landmark (e.g. opposite the yellow gate)" maxLength={300} defaultValue={data.location?.landmark ?? ''} aria-label="Landmark" />
        <input style={input} name="plus_code" placeholder="Plus code (optional, e.g. 6FR6C8F7+2X)" maxLength={20} defaultValue={data.location?.plus_code ?? ''} aria-label="Plus code" />
        <input style={input} name="delivery_notes" placeholder="Notes for the driver" maxLength={1000} aria-label="Delivery notes" />
        <select style={input} name="recipient_available" defaultValue="" aria-label="Will someone be available?">
          <option value="">Will someone be available to receive it?</option><option value="yes">Yes</option><option value="no">No - please call me</option>
        </select>
        <button type="submit" disabled={busy} style={{ ...input, background: 'var(--teal, #1f6f68)', color: '#fff', border: 0, cursor: 'pointer', fontWeight: 600 }}>{busy ? 'Sending…' : 'Send details'}</button>
      </form>
    </section>}

    {message && <p role="status" style={{ marginBottom: 16 }}>{message}</p>}
    <p style={{ fontSize: 12, color: 'var(--muted, #6b7a79)' }}>
      Don&apos;t want delivery texts for this order?{' '}
      <button onClick={() => send('consent', { purpose: 'sms', granted: false }, 'You will not receive further text messages.')} disabled={busy} style={{ background: 'none', border: 0, padding: 0, textDecoration: 'underline', cursor: 'pointer', color: 'inherit', font: 'inherit' }}>Stop SMS</button>
    </p>
  </main>;
}
