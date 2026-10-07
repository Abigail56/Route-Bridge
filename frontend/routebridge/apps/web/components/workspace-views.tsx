'use client';

import { describeAutoAssign } from '../lib/dispatch-text';
import { Avatar } from './avatar';
import { DriverAccessDialog } from './driver-access';
import { makeAvatar } from '../lib/avatar';
import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { friendlyMessage, type ApiClient, type Driver, type Merchant, type MyTenant, type OrderInput, type ReconciliationItem, type Zone } from '../lib/api';
import { NEXT_STATUSES, toAmount, type Job } from '../lib/jobs';

const money = new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN', maximumFractionDigits: 0 });
const statusLabel = (value: string) => value.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());

type Props = { api: ApiClient; tenantId: string; onChanged: () => void };

function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError('');
    try { await fn(); return true; } catch (exc) { setError(friendlyMessage(exc)); return false; } finally { setBusy(false); }
  };
  return { busy, error, run };
}

function Modal({ title, close, children }: { title: string; close: () => void; children: ReactNode }) {
  return <div className="drawer-backdrop" onClick={close}><aside className="drawer" onClick={(event) => event.stopPropagation()}><button className="close" onClick={close} aria-label="Close">×</button><h2>{title}</h2>{children}</aside></div>;
}

const fieldStyle = { display: 'grid', gap: 4, marginBottom: 12 } as const;
const inputStyle = { padding: '8px 10px', borderRadius: 8, border: '1px solid var(--border, #d0d5dd)', background: 'transparent', color: 'inherit', font: 'inherit' } as const;

export function NewOrderModal({ api, tenantId, onChanged, close }: Props & { close: () => void }) {
  const [merchants, setMerchants] = useState<Merchant[]>([]);
  const [zones, setZones] = useState<Zone[]>([]);
  const [loadError, setLoadError] = useState('');
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const { busy, error, run } = useAction();
  useEffect(() => {
    api.getMerchants(tenantId).then(setMerchants).catch((exc) => setLoadError(friendlyMessage(exc)));
    api.getZones(tenantId).then(setZones).catch(() => setZones([]));
  }, [api, tenantId]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const get = (name: string) => String(form.get(name) ?? '').trim();
    const input: OrderInput = {
      merchant_id: get('merchant_id'), customer_name: get('customer_name'), customer_phone: get('customer_phone'), external_ref: get('external_ref'),
      total_amount: get('total_amount') || '0', cod_amount: get('cod_amount') || '0', address_text: get('address_text'),
      landmark: get('landmark') || undefined, delivery_notes: get('delivery_notes') || undefined,
      location_confidence: get('location_confidence') as OrderInput['location_confidence'],
      plus_code: get('plus_code') || undefined,
      recipient_available: get('recipient_available') ? get('recipient_available') === 'yes' : undefined,
      service_zone_id: get('service_zone_id') || undefined,
      window_start: get('window_start') ? new Date(get('window_start')).toISOString() : undefined,
      window_end: get('window_end') ? new Date(get('window_end')).toISOString() : undefined,
    };
    if (await run(() => api.createOrder(tenantId, input, idempotencyKey))) { onChanged(); close(); }
  }

  const field = (label: string, name: string, extra: Record<string, unknown> = {}) => <label style={fieldStyle}><span className="eyebrow">{label}</span><input name={name} style={inputStyle} {...extra} /></label>;
  return <Modal title="New order" close={close}>
    <form onSubmit={submit}>
      <label style={fieldStyle}><span className="eyebrow">MERCHANT</span><select name="merchant_id" required style={inputStyle} defaultValue="">
        <option value="" disabled>{merchants.length ? 'Select a merchant' : 'No merchants yet - add one in Settings > Merchants'}</option>{merchants.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
      </select></label>
      {field('ORDER REFERENCE', 'external_ref', { required: true, maxLength: 100 })}
      {field('CUSTOMER NAME', 'customer_name', { required: true, maxLength: 200 })}
      {field('CUSTOMER PHONE', 'customer_phone', { required: true, minLength: 5, maxLength: 30, inputMode: 'tel' })}
      {field('ADDRESS', 'address_text', { required: true, maxLength: 500 })}
      {field('LANDMARK', 'landmark', { maxLength: 300, placeholder: 'e.g. Opposite the yellow supermarket sign' })}
      {field('DELIVERY NOTES', 'delivery_notes', { maxLength: 1000 })}
      {field('ORDER TOTAL (NGN)', 'total_amount', { type: 'number', min: 0, step: '0.01', defaultValue: '0' })}
      {field('COD AMOUNT (NGN)', 'cod_amount', { type: 'number', min: 0, step: '0.01', defaultValue: '0' })}
      <label style={fieldStyle}><span className="eyebrow">LOCATION CONFIDENCE</span><select name="location_confidence" style={inputStyle} defaultValue="unverified">
        <option value="unverified">Unverified</option><option value="geocoded">Geocoded</option><option value="customer_confirmed">Customer confirmed</option><option value="driver_confirmed">Driver confirmed</option>
      </select></label>
      {field('PLUS CODE (OPTIONAL)', 'plus_code', { maxLength: 20, placeholder: 'e.g. 6FR6C8F7+2X' })}
      <label style={fieldStyle}><span className="eyebrow">WILL SOMEONE BE AVAILABLE?</span><select name="recipient_available" style={inputStyle} defaultValue=""><option value="">Unknown</option><option value="yes">Yes</option><option value="no">No</option></select></label>
      {zones.length > 0 && <label style={fieldStyle}><span className="eyebrow">SERVICE ZONE</span><select name="service_zone_id" style={inputStyle} defaultValue=""><option value="">No zone</option>{zones.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}</select></label>}
      {field('DELIVERY WINDOW START', 'window_start', { type: 'datetime-local' })}
      {field('DELIVERY WINDOW END', 'window_end', { type: 'datetime-local' })}
      {(error || loadError) && <p role="alert" className="low-confidence">{error || loadError}</p>}
      <div className="drawer-actions"><button className="button primary" type="submit" disabled={busy || !merchants.length}>{busy ? 'Creating…' : 'Create order'}</button><button className="button secondary" type="button" onClick={close}>Cancel</button></div>
    </form>
  </Modal>;
}

export function JobDrawer({ job, api, tenantId, onChanged, close }: Props & { job: Job; close: () => void }) {
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [driverId, setDriverId] = useState('');
  const { busy, error, run } = useAction();
  const [autoMessage, setAutoMessage] = useState('');
  const canAssign = job.jobId && (job.rawStatus === 'pending' || job.rawStatus === 'rescheduled');
  useEffect(() => { if (canAssign) api.getDrivers(tenantId).then(setDrivers).catch(() => setDrivers([])); }, [api, tenantId, canAssign]);

  const act = (fn: () => Promise<unknown>) => run(fn).then((ok) => { if (ok) { onChanged(); close(); } });
  const moves = job.jobId ? NEXT_STATUSES[job.rawStatus] ?? [] : [];
  return <div className="drawer-backdrop" onClick={close}><aside className="drawer" onClick={(event) => event.stopPropagation()}>
    <button className="close" onClick={close} aria-label="Close">×</button>
    <div className="breadcrumb">DELIVERY JOB</div><h2>{job.order}</h2>
    <span className={`status ${job.status === 'delivered' ? 'status-green' : job.status === 'exception' ? 'status-red' : job.status === 'pending' ? 'status-neutral' : 'status-blue'}`}><i />{statusLabel(job.rawStatus)}</span>
    <div className="drawer-block"><span className="eyebrow">CUSTOMER</span><b>{job.customer}</b><small>{job.merchant}</small><small>{job.area}{job.landmark ? ` · ${job.landmark}` : ''}</small>
      <small className={job.confidence === 'Low' ? 'low-confidence' : ''}>Location confidence: {job.confidence}{job.score !== null ? ` (${job.score}/100)` : ''}{job.corrected ? ' · corrected, original kept' : ''}</small>
      {job.plusCode && <small>Plus code: {job.plusCode}</small>}
      {job.windowStart && <small>Window: {new Date(job.windowStart.endsWith('Z') ? job.windowStart : `${job.windowStart}Z`).toLocaleString('en-NG', { dateStyle: 'short', timeStyle: 'short' })} – {job.windowEnd ? new Date(job.windowEnd.endsWith('Z') ? job.windowEnd : `${job.windowEnd}Z`).toLocaleTimeString('en-NG', { timeStyle: 'short' }) : ''}</small>}
    </div>
    <div className="drawer-block"><span className="eyebrow">ASSIGNED DRIVER</span>{job.driver ? <b>{job.driver}</b> : <span className="unassigned">Needs assignment</span>}
      {canAssign && <div style={{ marginTop: 8 }}>
        <button className="button primary" disabled={busy} onClick={async () => {
          const ok = await run(async () => {
            const result = await api.autoAssignJob(tenantId, job.jobId!);
            setAutoMessage(describeAutoAssign(result));
            if (!result.assigned) throw new Error(describeAutoAssign(result));
          });
          if (ok) { onChanged(); setTimeout(close, 2200); }
        }}>Assign nearest driver</button>
        {autoMessage && <p role="status" style={{ margin: '8px 0 0' }}>{autoMessage}</p>}
        <small className="muted" style={{ display: 'block', marginTop: 6 }}>Or choose a driver yourself:</small>
      </div>}
      {canAssign && <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
        <select value={driverId} onChange={(event) => setDriverId(event.target.value)} style={inputStyle} aria-label="Driver"><option value="">{drivers.length ? 'Choose a driver' : 'No drivers yet'}</option>{drivers.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select>
        <button className="button primary" disabled={busy || !driverId} onClick={() => act(() => api.assignDriver(tenantId, job.jobId!, driverId))}>Assign</button>
      </div>}
    </div>
    <div className="drawer-block"><span className="eyebrow">PAYMENT</span><div className="payment-row"><b>{money.format(job.amount)}</b><span>COD</span></div><small className="muted">Expected amount is separate from delivery proof.</small></div>
    {moves.length > 0 && <div className="drawer-block"><span className="eyebrow">MOVE JOB TO</span><div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 4 }}>
      {moves.map((target) => <button key={target} className="button secondary" disabled={busy} onClick={() => act(() => api.transitionJob(tenantId, job.jobId!, target, target === 'failed_attempt' ? 'recipient_unreachable' : undefined))}>{statusLabel(target)}</button>)}
    </div></div>}
    {job.jobId && <LocationAndTracking job={job} api={api} tenantId={tenantId} onChanged={onChanged} />}
    {error && <p role="alert" className="low-confidence">{error}</p>}
    <div className="drawer-actions"><button className="button secondary" onClick={close}>Close</button></div>
  </aside></div>;
}

function LocationAndTracking({ job, api, tenantId, onChanged }: Props & { job: Job }) {
  const { busy, error, run } = useAction();
  const [token, setToken] = useState(job.trackingToken);
  const [copied, setCopied] = useState(false);
  const link = token ? `${window.location.origin}/track/${token}` : '';

  async function correct(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    const body: Record<string, unknown> = { reason: 'operator correction' };
    for (const key of ['landmark', 'plus_code', 'delivery_notes']) {
      const value = String(form.get(key) ?? '').trim();
      if (value) body[key] = value;
    }
    if (Object.keys(body).length === 1) return;
    if (await run(() => api.correctLocation(tenantId, job.jobId!, body))) { formEl.reset(); onChanged(); }
  }
  async function copy() {
    try { await navigator.clipboard.writeText(link); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* clipboard unavailable */ }
  }

  return <>
    <div className="drawer-block"><span className="eyebrow">CUSTOMER TRACKING LINK</span>
      {link ? <small style={{ wordBreak: 'break-all' }}>{link}</small> : <small className="muted">No active link.</small>}
      <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
        {link && <button className="button secondary" type="button" onClick={copy}>{copied ? 'Copied' : 'Copy link'}</button>}
        <button className="button secondary" type="button" disabled={busy} onClick={async () => { let fresh = ''; if (await run(async () => { fresh = (await api.reissueTrackingLink(tenantId, job.jobId!)).tracking_token; })) { setToken(fresh); onChanged(); } }}>Reissue</button>
      </div>
    </div>
    <div className="drawer-block"><span className="eyebrow">CORRECT LOCATION (ORIGINAL IS KEPT)</span>
      <form onSubmit={correct} style={{ display: 'grid', gap: 6, marginTop: 4 }}>
        <input name="landmark" placeholder="Landmark" maxLength={300} style={inputStyle} aria-label="Corrected landmark" />
        <input name="plus_code" placeholder="Plus code" maxLength={20} style={inputStyle} aria-label="Corrected plus code" />
        <input name="delivery_notes" placeholder="Delivery notes" maxLength={1000} style={inputStyle} aria-label="Corrected notes" />
        <button className="button secondary" type="submit" disabled={busy}>Save correction</button>
      </form>
      {error && <p role="alert" className="low-confidence">{error}</p>}
    </div>
  </>;
}

export function DriversView({ api, tenantId }: Omit<Props, 'onChanged'>) {
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [loadError, setLoadError] = useState('');
  const { busy, error, run } = useAction();
  const [accessFor, setAccessFor] = useState<Driver | null>(null);
  const load = useCallback(() => api.getDrivers(tenantId).then((rows) => { setDrivers(rows); setLoadError(''); }).catch((exc) => setLoadError(friendlyMessage(exc))), [api, tenantId]);
  useEffect(() => { load(); }, [load]);

  async function changePhoto(driver: Driver, file: File) {
    const ok = await run(async () => api.setDriverPhoto(tenantId, driver.id, await makeAvatar(file)));
    if (ok) load();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    const ok = await run(() => api.createDriver(tenantId, { name: String(form.get('name')).trim(), phone: String(form.get('phone')).trim(), fleet_type: String(form.get('fleet_type')) }));
    if (ok) { formEl.reset(); load(); }
  }
  return <div className="card" style={{ padding: 16 }}>
    <form onSubmit={submit} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
      <input name="name" placeholder="Driver name" required maxLength={200} style={inputStyle} aria-label="Driver name" />
      <input name="phone" placeholder="Phone" required minLength={5} maxLength={30} inputMode="tel" style={inputStyle} aria-label="Phone" />
      <select name="fleet_type" defaultValue="contracted" style={inputStyle} aria-label="Fleet type"><option value="owned">Owned</option><option value="contracted">Contracted</option><option value="partner">Partner</option></select>
      <button className="button primary" type="submit" disabled={busy}>Add driver</button>
    </form>
    {(error || loadError) && <p role="alert" className="low-confidence">{error || loadError}</p>}
    {accessFor && <DriverAccessDialog api={api} tenantId={tenantId} driver={accessFor} close={() => setAccessFor(null)} />}
    <div className="table-scroll"><table><thead><tr><th>DRIVER</th><th>PHONE</th><th>FLEET</th><th>STATUS</th><th /></tr></thead><tbody>
      {drivers.length === 0 && <tr><td colSpan={5} className="muted">No drivers yet.</td></tr>}
      {drivers.map((d) => <tr key={d.id}><td><span style={{ display: 'inline-flex', alignItems: 'center', gap: 10 }}><Avatar name={d.name} photo={d.photo} /><b>{d.name}</b></span></td><td>{d.phone}</td><td>{statusLabel(d.fleet_type)}</td><td>{statusLabel(d.status)}</td><td style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}><label className="button secondary" style={{ cursor: 'pointer' }}>{d.photo ? 'Change photo' : 'Add photo'}<input type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ''; if (file) changePhoto(d, file); }} /></label>{d.photo && <button className="button secondary" onClick={() => run(() => api.removeDriverPhoto(tenantId, d.id)).then((ok) => { if (ok) load(); })}>Remove photo</button>}<button className="button primary" onClick={() => setAccessFor(d)}>Access link &amp; QR</button>{d.status !== 'busy' && <button className="button secondary" disabled={busy} onClick={() => run(() => api.updateDriver(tenantId, d.id, { status: d.status === 'offline' ? 'available' : 'offline' })).then((ok) => { if (ok) load(); })}>{d.status === 'offline' ? 'Set available' : 'Set offline'}</button>}</td></tr>)}
    </tbody></table></div>
  </div>;
}

export function ReconciliationView({ api, tenantId, items, onChanged }: Props & { items: ReconciliationItem[] }) {
  const { busy, error, run } = useAction();
  const [notes, setNotes] = useState<Record<string, string>>({});
  return <div className="card" style={{ padding: 16 }}>
    {error && <p role="alert" className="low-confidence">{error}</p>}
    <div className="table-scroll"><table><thead><tr><th>ITEM</th><th>VARIANCE</th><th>STATUS</th><th>RESOLUTION</th></tr></thead><tbody>
      {items.length === 0 && <tr><td colSpan={4} className="muted">Nothing to reconcile.</td></tr>}
      {items.map((item) => <tr key={item.id}>
        <td><b>{item.id.slice(0, 8)}</b><small>{new Date(item.created_at.endsWith('Z') ? item.created_at : `${item.created_at}Z`).toLocaleDateString()}</small></td>
        <td><b>{money.format(toAmount(item.variance_amount))}</b></td>
        <td>{statusLabel(item.status)}</td>
        <td>{item.status === 'open'
          ? <span style={{ display: 'flex', gap: 8 }}><input style={inputStyle} placeholder="Resolution note" aria-label="Resolution note" value={notes[item.id] ?? ''} onChange={(event) => setNotes({ ...notes, [item.id]: event.target.value })} /><button className="button secondary" disabled={busy || !(notes[item.id] ?? '').trim()} onClick={() => run(() => api.resolveReconciliation(tenantId, item.id, notes[item.id].trim())).then((ok) => ok && onChanged())}>Resolve</button></span>
          : <small>{item.resolution_note}</small>}</td>
      </tr>)}
    </tbody></table></div>
  </div>;
}

export function SettingsView({ tenant }: { tenant: MyTenant | null }) {
  return <div className="card" style={{ padding: 16 }}>
    <div className="drawer-block"><span className="eyebrow">WORKSPACE</span><b>{tenant?.name || '—'}</b><small>{tenant?.tenant_id}</small></div>
    <div className="drawer-block"><span className="eyebrow">YOUR ROLE</span><b>{tenant?.role ? statusLabel(tenant.role) : '—'}</b></div>
    <small className="muted">Users, service zones, rate cards and delivery windows are not yet configurable from the console.</small>
  </div>;
}
