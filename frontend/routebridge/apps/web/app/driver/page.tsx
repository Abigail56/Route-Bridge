'use client';

import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { createDriverClient, DriverApiError, parseDriverToken, type DriverJob, type DriverSession } from '../../lib/driver/api';
import { DriverPush } from '../../components/driver-push';
import { compressImage } from '../../lib/driver/image';
import { navigationLinks } from '../../lib/driver/navigate';
import { enqueue, enqueueLocation, queueSize, readQueue, removeItem, type SyncEvent } from '../../lib/driver/queue';
import { clearAll, kvGet, kvSet, secureDelete, secureGet, secureSet } from '../../lib/driver/store';
import { backoffMs, syncOnce, type SyncOutcome } from '../../lib/driver/sync';

const FAIL_REASONS = [['recipient_unreachable', 'Customer not reachable'], ['address_not_found', 'Address not found'], ['recipient_unavailable', 'Nobody to receive'], ['refused_delivery', 'Customer refused'], ['unsafe_location', 'Unsafe location'], ['vehicle_issue', 'Vehicle problem']] as const;
const NEXT: Record<string, { to: string; label: string }> = { assigned: { to: 'accepted', label: 'Accept job' }, rescheduled: { to: 'accepted', label: 'Accept job' }, accepted: { to: 'en_route', label: 'Start trip' }, en_route: { to: 'arrived', label: "I've arrived" } };

const ui = {
  page: { maxWidth: 520, margin: '0 auto', padding: '0 14px 80px', font: '16px/1.4 system-ui, sans-serif', color: '#0f2744', minHeight: '100vh' },
  card: { border: '1px solid #dde5ee', borderRadius: 16, padding: 16, marginBottom: 12, background: '#fff', color: '#0f2744', boxShadow: '0 4px 16px rgba(15,39,68,.07)' },
  btn: { padding: '15px 16px', borderRadius: 12, border: 0, background: '#ff7a29', color: '#0f2744', font: '800 16px system-ui', width: '100%', cursor: 'pointer', boxShadow: '0 2px 8px rgba(255,122,41,.35)', marginBottom: 12 },
  ghost: { padding: '12px 14px', borderRadius: 12, border: '1.5px solid #0f2744', background: '#fff', color: '#0f2744', font: '700 15px system-ui', cursor: 'pointer' },
  input: { width: '100%', padding: 12, borderRadius: 10, border: '1px solid #c9d6e4', font: '16px system-ui', marginBottom: 8, boxSizing: 'border-box' as const, background: '#fff', color: '#0f2744' },
  // the navy band at the top of every screen, running to the screen edges
  band: { margin: '0 -14px 14px', padding: '16px 16px 14px', background: 'linear-gradient(135deg,#0f2744,#173b66)', color: '#fff', borderRadius: '0 0 20px 20px', boxShadow: '0 6px 20px rgba(15,39,68,.28)' },
  pill: { display: 'inline-block', padding: '3px 10px', borderRadius: 999, background: '#ffede0', color: '#9a3412', fontSize: 12, fontWeight: 700, textTransform: 'capitalize' as const },
};
const money = (value: string | null) => (value ? `₦${Number(value).toLocaleString('en-NG')}` : '');

export default function DriverApp() {
  const [session, setSession] = useState<DriverSession | null>(null);
  const [expiresAt, setExpiresAt] = useState(0);
  const [ready, setReady] = useState(false);
  const [online, setOnline] = useState(true);
  const [jobs, setJobs] = useState<DriverJob[]>([]);
  const [local, setLocal] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(0);
  const [flagged, setFlagged] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const onDeliveryRef = useRef(false);
  onDeliveryRef.current = jobs.some((job) => ['assigned', 'accepted', 'en_route', 'arrived'].includes(job.status));
  const [note, setNote] = useState('');
  const [dial, setDial] = useState<{ jobId: string; number: string } | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [authLost, setAuthLost] = useState(false);
  const busy = useRef(false);
  const failures = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const deviceId = useRef('');

  const client = useMemo(() => (session ? createDriverClient(session) : null), [session]);

  const refreshCounts = useCallback(async () => {
    const all = await readQueue();
    setPending(all.filter((e) => !e.item.rejected).length);
    setFlagged(all.filter((e) => e.item.rejected).length);
  }, []);

  // ---- boot: load the session and cached jobs, register the offline shell -----------------------------------------
  useEffect(() => {
    (async () => {
      setOnline(navigator.onLine);
      if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => undefined);
      deviceId.current = (await kvGet<string>('device-id')) ?? crypto.randomUUID();
      await kvSet('device-id', deviceId.current);
      // a token can arrive in the URL hash (QR code / link from dispatch): #token=...
      const hashToken = new URLSearchParams(window.location.hash.slice(1)).get('token');
      if (hashToken) { await acceptToken(hashToken); history.replaceState(null, '', window.location.pathname); }
      else {
        const stored = await secureGet<DriverSession>('session');
        if (stored) { setSession(stored); setExpiresAt(parseDriverToken(stored.token)?.expiresAt ?? 0); setJobs((await secureGet<DriverJob[]>('jobs')) ?? []); }
      }
      await refreshCounts();
      setReady(true);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function acceptToken(raw: string) {
    const parsed = parseDriverToken(raw.trim());
    if (!parsed) { setNote('That token is not valid. Ask dispatch for a new one.'); return; }
    if (parsed.expiresAt < Date.now()) { setNote('That token has expired. Ask dispatch for a new one.'); return; }
    const next: DriverSession = { token: raw.trim(), tenantId: parsed.tenantId, driverId: parsed.driverId };
    await secureSet('session', next);
    setSession(next); setExpiresAt(parsed.expiresAt); setAuthLost(false); setNote('');
  }

  // ---- sync -------------------------------------------------------------------------------------------------------
  const runSync = useCallback(async () => {
    if (!client || busy.current) return;
    busy.current = true;
    setSyncing(true);
    let outcome: SyncOutcome = 'offline';
    let retryAfter: number | undefined;
    try {
      const result = await syncOnce(client);
      outcome = result.outcome; retryAfter = result.retryAfter;
      if (outcome === 'auth') setAuthLost(true);
      if (outcome === 'ok' && result.remaining === 0) {
        const fresh = await client.jobs().catch((error) => { if (error instanceof DriverApiError && (error.status === 401 || error.status === 403)) setAuthLost(true); return null; });
        if (fresh) { setJobs(fresh); setLocal({}); await secureSet('jobs', fresh); }
      }
    } finally {
      busy.current = false;
      setSyncing(false);
      await refreshCounts();
    }
    failures.current = outcome === 'ok' ? 0 : failures.current + 1;
    if (timer.current) clearTimeout(timer.current);
    if (outcome !== 'auth') timer.current = setTimeout(runSync, outcome === 'ok' ? 30_000 : backoffMs(failures.current, retryAfter));
  }, [client, refreshCounts]);

  useEffect(() => {
    if (!client) return;
    const onOnline = () => { setOnline(true); runSync(); };
    const onOffline = () => setOnline(false);
    window.addEventListener('online', onOnline); window.addEventListener('offline', onOffline);
    runSync();
    return () => { window.removeEventListener('online', onOnline); window.removeEventListener('offline', onOffline); if (timer.current) clearTimeout(timer.current); };
  }, [client, runSync]);

  // ---- GPS pings (newest one wins in the queue) -------------------------------------------------------------------
  useEffect(() => {
    if (!session || !navigator.geolocation) return;
    let last = 0;
    const id = navigator.geolocation.watchPosition((pos) => {
      // quick updates while a delivery is under way so dispatchers and customers see a moving rider; relaxed otherwise to save battery
      if (Date.now() - last < (onDeliveryRef.current ? 15_000 : 60_000)) return;
      last = Date.now();
      enqueueLocation(buildEvent('driver.location', 'driver', session.driverId, { latitude: pos.coords.latitude, longitude: pos.coords.longitude })).then(refreshCounts);
    }, () => undefined, { enableHighAccuracy: false, maximumAge: 30_000, timeout: 20_000 });
    return () => navigator.geolocation.clearWatch(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]);

  function buildEvent(type: SyncEvent['event_type'], aggregate: SyncEvent['aggregate_type'], aggregateId: string, payload: Record<string, unknown>): SyncEvent {
    return { event_id: crypto.randomUUID(), device_id: deviceId.current, event_type: type, aggregate_type: aggregate, aggregate_id: aggregateId, payload, occurred_at: new Date().toISOString() };
  }
  async function emit(type: SyncEvent['event_type'], jobId: string, payload: Record<string, unknown>, photo?: Blob) {
    await enqueue(buildEvent(type, 'delivery_job', jobId, payload), photo);
    await refreshCounts();
    runSync();
  }

  const statusOf = (job: DriverJob) => local[job.job_id] ?? job.status;
  const visible = jobs.filter((job) => !['delivered', 'cancelled', 'returned'].includes(statusOf(job)));
  const current = visible.find((job) => job.job_id === selected) ?? null;

  async function advance(job: DriverJob) {
    const step = NEXT[statusOf(job)];
    if (!step) return;
    setLocal((state) => ({ ...state, [job.job_id]: step.to }));
    await emit('delivery.transition', job.job_id, { target_status: step.to });
  }

  async function complete(event: FormEvent<HTMLFormElement>, job: DriverJob) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const code = String(form.get('otp') ?? '').trim();
    const file = form.get('photo') as File | null;
    if (!code && !(file && file.size)) { setNote("Enter the customer's code or take a photo as proof."); return; }
    const photo = file && file.size ? await compressImage(file) : undefined;
    await emit('delivery.proof', job.job_id, { ...(code ? { otp_code: code } : {}), recipient_name: String(form.get('recipient') ?? '').trim() || undefined }, photo);
    const collected = String(form.get('collected') ?? '').trim();
    if (collected && Number(job.cod_amount ?? 0) > 0) await emit('delivery.payment', job.job_id, { collected_amount: collected, method: 'cod' });
    setLocal((state) => ({ ...state, [job.job_id]: 'delivered' })); setSelected(null); setNote('Delivery saved. It will sync automatically.');
  }

  async function failed(event: FormEvent<HTMLFormElement>, job: DriverJob) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await emit('delivery.transition', job.job_id, { target_status: 'failed_attempt', reason_code: String(form.get('reason')), notes: String(form.get('notes') ?? '') || undefined });
    setLocal((state) => ({ ...state, [job.job_id]: 'failed_attempt' })); setSelected(null); setNote('Failed attempt recorded.');
  }

  async function correction(event: FormEvent<HTMLFormElement>, job: DriverJob) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload: Record<string, unknown> = {};
    for (const key of ['landmark', 'plus_code']) { const value = String(form.get(key) ?? '').trim(); if (value) payload[key] = value; }
    if (form.get('here') === 'on' && navigator.geolocation) {
      const pos = await new Promise<GeolocationPosition | null>((resolve) => navigator.geolocation.getCurrentPosition(resolve, () => resolve(null), { timeout: 10_000 }));
      if (pos) { payload.latitude = pos.coords.latitude; payload.longitude = pos.coords.longitude; }
    }
    if (!Object.keys(payload).length) return;
    await emit('location.correction', job.job_id, payload);
    event.currentTarget.reset(); setNote('Location correction saved (the original address is kept).');
  }

  async function requestCode(job: DriverJob) {
    try {
      const result = await client!.requestOtp(job.job_id);
      setNote(result.relay ? 'Dispatch has been told. They will send the customer the code. Ask the customer for it when you hand over the parcel.' : 'The customer has been texted a delivery code. Ask them for it when you hand over the parcel.');
    } catch (error) { setNote(error instanceof DriverApiError ? error.message : 'You need a connection to ask for the code.'); }
  }

  async function callNow(job: DriverJob) {
    try {
      const result = await client!.callCustomer(job.job_id);
      if (result.dial_number) { setDial({ jobId: job.job_id, number: result.dial_number }); setNote(''); window.location.href = `tel:${result.dial_number}`; }
      else setNote('Connecting the call. Your phone will ring.');
    } catch (error) { setNote(error instanceof DriverApiError ? error.message : 'You need a connection to call.'); }
  }

  async function online_action(label: string, fn: () => Promise<unknown>) {
    try { await fn(); setNote(`${label} requested.`); } catch (error) { setNote(error instanceof DriverApiError ? error.message : 'You need a connection for this.'); }
  }

  async function signOut() {
    if (pending && !confirm(`${pending} update(s) have not synced yet and will be lost. Sign out anyway?`)) return;
    await secureDelete('session'); await clearAll(); setSession(null); setJobs([]); setPending(0); setFlagged(0);
  }

  async function dismissFlagged() {
    for (const entry of await readQueue()) if (entry.item.rejected) await removeItem(entry.seq, entry.item.photoId);
    await refreshCounts();
  }

  if (!ready) return <main className="rb-driver" style={ui.page}>Loading…</main>;

  if (!session) return <main className="rb-driver" style={ui.page}>
    <div style={{ ...ui.band, padding: '38px 22px 30px', borderRadius: '0 0 26px 26px', background: "linear-gradient(180deg,rgba(10,28,51,.9),rgba(15,39,68,.78)),url('/routebridge-bg-sm.jpg') 72% center/cover no-repeat,#0f2744" }}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/driver-icon-192.png" alt="" width={54} height={54} style={{ borderRadius: 14, display: 'block' }} />
      <h1 style={{ fontSize: 28, margin: '14px 0 6px' }}>RouteBridge Driver</h1>
      <p style={{ margin: 0, color: '#d6e2f0' }}>Paste the access token from dispatch, or open the link/QR code they send you.</p>
    </div>
    <form onSubmit={(event) => { event.preventDefault(); acceptToken(String(new FormData(event.currentTarget).get('token') ?? '')); }}>
      <textarea name="token" rows={4} style={ui.input} placeholder="Access token" aria-label="Access token" />
      <button style={ui.btn} type="submit">Sign in</button>
    </form>
    {note && <p role="alert" style={{ color: '#b3261e' }}>{note}</p>}
  </main>;

  return <main className="rb-driver" style={ui.page}>
    <header style={{ ...ui.band, position: 'sticky', top: 0, zIndex: 5, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
      <b style={{ fontSize: 20 }}>My deliveries</b>
      <span style={{ fontSize: 13, padding: '6px 12px', borderRadius: 999, background: online ? 'rgba(255,255,255,.14)' : 'rgba(255,122,41,.3)', border: '1px solid rgba(255,255,255,.28)' }}>{online ? '● Online' : '○ Offline'} · {pending ? `${pending} to sync` : 'All synced'}{syncing ? ' …' : ''}</span>
    </header>
    {client && <DriverPush client={client} />}
    {expiresAt > 0 && expiresAt < Date.now() + 3600_000 && <div role="alert" style={{ ...ui.card, background: '#fff6e0' }}>Your sign-in {expiresAt < Date.now() ? 'has expired' : 'expires soon'}. Ask dispatch for a new token. Saved updates stay on this phone until you reconnect.</div>}
    {authLost && <div role="alert" style={{ ...ui.card, background: '#fde8e8' }}>Dispatch has signed this device out. Your {pending} saved update(s) are kept; paste a new token to continue.<form onSubmit={(event) => { event.preventDefault(); acceptToken(String(new FormData(event.currentTarget).get('token') ?? '')); }} style={{ marginTop: 8 }}><input name="token" style={ui.input} placeholder="New access token" aria-label="New access token" /><button style={ui.btn} type="submit">Continue</button></form></div>}
    {flagged > 0 && <div role="alert" style={{ ...ui.card, background: '#fff6e0' }}>{flagged} update(s) were refused by the server (usually because the job changed). <button style={ui.ghost} onClick={dismissFlagged}>Dismiss</button></div>}
    {note && <p role="status" style={{ fontSize: 14 }}>{note}</p>}

    {!current && <>
      {visible.length === 0 && <p>No active jobs. New assignments appear here when you are online.</p>}
      {visible.map((job) => <button key={job.job_id} onClick={() => { setSelected(job.job_id); setNote(''); }} style={{ ...ui.card, width: '100%', textAlign: 'left', cursor: 'pointer', borderLeft: '5px solid #ff7a29' }}>
        <b style={{ fontSize: 17 }}>{job.reference}</b> <span style={ui.pill}>{statusOf(job).replace(/_/g, ' ')}</span><br />{job.customer_name}<br /><small>{job.address}{job.landmark ? ` · ${job.landmark}` : ''}</small>
        {Number(job.cod_amount ?? 0) > 0 && <div><b>Collect {money(job.cod_amount)}</b></div>}
      </button>)}
    </>}

    {current && <section>
      <button style={{ ...ui.ghost, marginBottom: 10 }} onClick={() => setSelected(null)}>← All jobs</button>
      <div style={ui.card}>
        <h2 style={{ margin: '0 0 4px' }}>{current.reference}</h2>
        <div><span style={ui.pill}>{statusOf(current).replace(/_/g, ' ')}</span></div>
        <p><b>{current.customer_name}</b> <small>{current.customer_phone_masked}</small><br />{current.address}{current.landmark ? <><br />📍 {current.landmark}</> : null}{current.plus_code ? <><br />Plus code {current.plus_code}</> : null}</p>
        {current.recipient_available === false && <p style={{ color: '#b3261e' }}>Customer said nobody will be available.</p>}
        {current.location_score !== null && current.location_score < 45 && <p style={{ color: '#b3261e' }}>Weak location — confirm with the customer.</p>}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {(() => { const nav = navigationLinks({ latitude: current.latitude, longitude: current.longitude, address: current.address }); return <><a style={{ ...ui.ghost, textDecoration: 'none' }} href={nav.google} target="_blank" rel="noreferrer">Navigate</a><a style={{ ...ui.ghost, textDecoration: 'none' }} href={nav.waze} target="_blank" rel="noreferrer">Waze</a></>; })()}
          <button style={statusOf(current) === 'arrived' ? { ...ui.ghost, background: '#0f2744', color: '#fff' } : ui.ghost} disabled={!online || statusOf(current) !== 'arrived'} onClick={() => callNow(current)}>Call customer</button>
        </div>
        {statusOf(current) !== 'arrived' && <small style={{ display: 'block', marginTop: 8, color: '#566a82' }}>You can call the customer once you arrive.</small>}
        {dial && dial.jobId === current.job_id && <a href={`tel:${dial.number}`} style={{ ...ui.btn, display: 'block', textAlign: 'center', textDecoration: 'none', marginTop: 10, boxSizing: 'border-box' }}>📞 Tap to call {dial.number}</a>}
      </div>

      {NEXT[statusOf(current)] && <button style={ui.btn} onClick={() => advance(current)}>{NEXT[statusOf(current)].label}</button>}

      {statusOf(current) === 'arrived' && <>
        <form onSubmit={(event) => complete(event, current)} style={ui.card}>
          <b>Complete delivery</b>
          <button type="button" style={{ ...ui.ghost, margin: '8px 0', width: '100%' }} disabled={!online} onClick={() => requestCode(current)}>Text the customer a delivery code</button>
          <input name="otp" inputMode="numeric" maxLength={8} placeholder="Customer's 6-digit code" style={ui.input} aria-label="Delivery code" />
          <input name="recipient" placeholder="Received by (name)" style={ui.input} aria-label="Received by" />
          <input name="photo" type="file" accept="image/*" capture="environment" style={ui.input} aria-label="Delivery photo" />
          {Number(current.cod_amount ?? 0) > 0 && <input name="collected" type="number" step="0.01" min="0" defaultValue={current.cod_amount ?? ''} style={ui.input} aria-label="Cash collected" />}
          <button style={ui.btn} type="submit">Confirm delivered</button>
        </form>
        <form onSubmit={(event) => failed(event, current)} style={ui.card}>
          <b>Could not deliver?</b>
          <select name="reason" style={{ ...ui.input, marginTop: 8 }} aria-label="Reason">{FAIL_REASONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
          <input name="notes" placeholder="Notes (optional)" style={ui.input} aria-label="Notes" />
          <button style={ui.ghost} type="submit">Record failed attempt</button>
        </form>
      </>}

      <form onSubmit={(event) => correction(event, current)} style={ui.card}>
        <b>Fix the location</b> <small>(the original address is kept)</small>
        <input name="landmark" placeholder="Landmark" style={{ ...ui.input, marginTop: 8 }} aria-label="Corrected landmark" />
        <input name="plus_code" placeholder="Plus code" style={ui.input} aria-label="Corrected plus code" />
        <label style={{ display: 'block', marginBottom: 8 }}><input type="checkbox" name="here" /> Use my current GPS position</label>
        <button style={ui.ghost} type="submit">Save correction</button>
      </form>
    </section>}

    <footer style={{ marginTop: 24, display: 'flex', gap: 8 }}>
      <button style={ui.ghost} onClick={runSync} disabled={!online || syncing}>Sync now</button>
      <button style={ui.ghost} onClick={signOut}>Sign out</button>
    </footer>
  </main>;
}
