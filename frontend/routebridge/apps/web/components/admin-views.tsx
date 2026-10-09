'use client';

import { describeAutoAssign } from '../lib/dispatch-text';
import { RenameDialog } from './platform-views';
import { StaffClaims } from './claims-views';
import { MerchantDetailsPanel } from './merchant-registration';
import { StatementCard } from './statement-card';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { friendlyMessage, type ApiClient, type AuditRow, type Batch, type Driver, type ExceptionItem, type Member, type Merchant, type MyTenant, type OperatingArea, type RateCard, type StatementResult, type Summary, type Zone } from '../lib/api';

const money = new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN', maximumFractionDigits: 0 });
const pct = (value: number | null) => (value === null ? '—' : `${(value * 100).toFixed(1)}%`);
const label = (value: string) => value.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
const when = (iso: string | null) => (iso ? new Date(iso.endsWith('Z') || /[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`).toLocaleString('en-NG', { dateStyle: 'short', timeStyle: 'short' }) : '—');
const inputStyle = { padding: '8px 10px', borderRadius: 8, border: '1px solid var(--line, #d0d5dd)', background: 'transparent', color: 'inherit', font: 'inherit' } as const;
const ROLES = ['tenant_owner', 'tenant_admin', 'dispatcher', 'operations_manager', 'finance', 'merchant_user', 'partner_operator', 'read_only', 'driver'];

type Base = { api: ApiClient; tenantId: string };

function useLoad<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const reload = useCallback(() => fn().then((value) => { setData(value); setError(''); }).catch((exc) => setError(friendlyMessage(exc))), deps);
  useEffect(() => { reload(); }, [reload]);
  return { data, error, reload };
}

/** KPI + failure-reason panel backed by GET /reports/summary. */
export function InsightsPanel({ api, tenantId, refreshKey }: Base & { refreshKey: number }) {
  const { data, error, reload } = useLoad<Summary>(() => api.getSummary(tenantId), [api, tenantId, refreshKey]);
  useEffect(() => { reload(); }, [refreshKey, reload]);
  if (error) return <p role="alert" className="low-confidence">{error}</p>;
  if (!data) return null;
  const tile = (title: string, value: string, sub: string) => <div className="metric card" key={title}><div className="metric-label">{title}</div><div className="metric-value">{value}</div><span className="metric-sub">{sub}</span></div>;
  return <>
    <div className="metric-grid">
      {tile('On-time rate', pct(data.on_time_rate), data.on_time_sample ? `${data.on_time_sample} jobs with a delivery window` : 'needs delivery windows')}
      {tile('First-attempt success', pct(data.first_attempt_success_rate), `${data.jobs_delivered} delivered in ${data.period_days} days`)}
      {tile('Cost per stop', data.cost_per_stop ? money.format(Number(data.cost_per_stop)) : '—', data.cost_per_stop ? 'from zone rate cards' : 'add rate cards')}
      {tile('Stops per driver', data.stops_per_driver === null ? '—' : String(data.stops_per_driver), 'route utilisation')}
    </div>
    {data.failure_reasons.length > 0 && <div className="card" style={{ padding: 16, marginBottom: 24 }}>
      <b>Failure reasons by zone</b>
      <div className="table-scroll"><table><thead><tr><th>ZONE</th><th>REASON</th><th>COUNT</th></tr></thead><tbody>
        {data.failure_reasons.map((row, index) => <tr key={index}><td>{row.zone_name ?? 'No zone'}</td><td>{label(row.reason_code)}</td><td>{row.count}</td></tr>)}
      </tbody></table></div>
    </div>}
  </>;
}

/** Exception queue backed by GET /exceptions. */
export function ExceptionsPanel({ api, tenantId, refreshKey, onOpen }: Base & { refreshKey: number; onOpen: (orderId: string) => void }) {
  const { data, error, reload } = useLoad<ExceptionItem[]>(() => api.getExceptions(tenantId), [api, tenantId]);
  useEffect(() => { reload(); }, [refreshKey, reload]);
  if (error) return <p role="alert" className="low-confidence">{error}</p>;
  if (!data || data.length === 0) return null;
  return <div className="card" style={{ padding: 16, marginBottom: 24 }}>
    <b>Exception queue ({data.length})</b>
    <div className="table-scroll"><table><thead><tr><th>ORDER</th><th>ISSUE</th><th>DETAIL</th><th>SINCE</th></tr></thead><tbody>
      {data.slice(0, 20).map((item, index) => <tr key={index} onClick={() => item.order_id && onOpen(item.order_id)} style={{ cursor: item.order_id ? 'pointer' : 'default' }}>
        <td><b>{item.external_ref ?? '—'}</b></td>
        <td><span className={`status ${item.severity === 'high' ? 'status-red' : 'status-amber'}`}><i />{label(item.kind)}</span></td>
        <td>{item.detail}</td><td>{when(item.since)}</td>
      </tr>)}
    </tbody></table></div>
  </div>;
}

/** Zone/window batches with a suggested stop order and one-click driver assignment. */
export function DispatchBatches({ api, tenantId, onChanged, refreshKey }: Base & { onChanged: () => void; refreshKey: number }) {
  const { data, error, reload } = useLoad<Batch[]>(() => api.getBatches(tenantId), [api, tenantId]);
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [driverId, setDriverId] = useState('');
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [notice, setNotice] = useState('');
  const [autoBusy, setAutoBusy] = useState(false);
  async function autoAssignAll() {
    setAutoBusy(true);
    try {
      const result = await api.autoAssignAll(tenantId);
      const stuck = result.results.find((r) => !r.assigned && r.reason);
      setNotice(`${result.assigned} job${result.assigned === 1 ? '' : 's'} assigned automatically${result.waiting ? `; ${result.waiting} still waiting. ${stuck ? describeAutoAssign(stuck) : ''}` : '.'}`);
      reload(); onChanged();
    } catch (exc) { setNotice(friendlyMessage(exc)); } finally { setAutoBusy(false); }
  }
  useEffect(() => { reload(); }, [refreshKey, reload]);
  useEffect(() => { api.getDrivers(tenantId).then((rows) => setDrivers(rows.filter((d) => d.status !== 'offline'))).catch(() => setDrivers([])); }, [api, tenantId]);

  async function assign(batch: Batch) {
    const ids = batch.suggested_sequence.filter((id) => picked[id]);
    if (!ids.length || !driverId) return;
    try {
      const result = await api.assignBatch(tenantId, ids, driverId);
      setNotice(`Assigned ${result.assigned.length} job(s)${result.failed.length ? `; ${result.failed.length} failed: ${result.failed.map((f) => f.reason).join(', ')}` : ''}.`);
      setPicked({});
      reload();
      onChanged();
    } catch (exc) { setNotice(friendlyMessage(exc)); }
  }

  if (error) return <p role="alert" className="low-confidence">{error}</p>;
  if (!data) return null;
  return <div style={{ marginBottom: 24 }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 8 }}>
      <h2 style={{ margin: 0 }}>Unassigned batches</h2>
      {data.length > 0 && <button className="button primary" disabled={autoBusy} onClick={autoAssignAll}>{autoBusy ? 'Assigning…' : 'Assign all waiting jobs automatically'}</button>}
    </div>
    {notice && <p role="status">{notice}</p>}
    {data.length === 0 && <p className="muted">Nothing waiting for a driver.</p>}
    {data.map((batch, index) => <div className="card" key={index} style={{ padding: 16, marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div><b>{batch.zone_name ?? 'No zone'}</b><small style={{ display: 'block' }}>{batch.window_start ? `${when(batch.window_start)} – ${when(batch.window_end)}` : 'No delivery window'} · {batch.jobs.length} job(s)</small></div>
        <div style={{ display: 'flex', gap: 8 }}>
          <select style={inputStyle} value={driverId} onChange={(event) => setDriverId(event.target.value)} aria-label="Driver for batch"><option value="">Choose driver</option>{drivers.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select>
          <button className="button primary" disabled={!driverId || !batch.suggested_sequence.some((id) => picked[id])} onClick={() => assign(batch)}>Assign selected</button>
        </div>
      </div>
      <ol style={{ margin: '12px 0 0', paddingLeft: 20 }}>
        {batch.suggested_sequence.map((jobId) => { const job = batch.jobs.find((j) => j.job_id === jobId)!; return <li key={jobId} style={{ padding: '4px 0' }}>
          <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}><input type="checkbox" checked={!!picked[jobId]} onChange={(event) => setPicked({ ...picked, [jobId]: event.target.checked })} /><b>{job.external_ref}</b><span>{job.address_text}</span>{job.location_score !== null && job.location_score < 45 && <span className="low-confidence">weak location</span>}</label>
        </li>; })}
      </ol>
    </div>)}
  </div>;
}

/** Statement import (dual reconciliation) and payout CSV export. */
export function FinanceTools({ api, tenantId, onChanged }: Base & { onChanged: () => void }) {
  const [result, setResult] = useState<StatementResult | null>(null);
  const [error, setError] = useState('');
  const today = new Date().toISOString().slice(0, 10);
  const monthAgo = new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10);
  const [range, setRange] = useState({ from: monthAgo, to: today });

  async function onFile(file: File | undefined) {
    if (!file) return;
    setError('');
    try { setResult(await api.importStatement(tenantId, file)); onChanged(); } catch (exc) { setError(friendlyMessage(exc)); }
  }
  async function exportPayouts(event: FormEvent) {
    event.preventDefault();
    setError('');
    try {
      const blob = await api.downloadPayouts(tenantId, `${range.from}T00:00:00Z`, `${range.to}T23:59:59Z`);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url; link.download = `payouts-${range.from}-${range.to}.csv`; link.click();
      URL.revokeObjectURL(url);
    } catch (exc) { setError(friendlyMessage(exc)); }
  }
  return <div className="card" style={{ padding: 16, marginBottom: 16 }}>
    <b>Finance tools</b>
    <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginTop: 12 }}>
      <label style={{ display: 'grid', gap: 4 }}><span className="eyebrow">IMPORT BANK / GATEWAY STATEMENT (CSV: reference, amount)</span><input type="file" accept=".csv,text/csv" onChange={(event) => onFile(event.target.files?.[0])} /></label>
      <form onSubmit={exportPayouts} style={{ display: 'flex', gap: 8, alignItems: 'end' }}>
        <label style={{ display: 'grid', gap: 4 }}><span className="eyebrow">PAYOUTS FROM</span><input type="date" style={inputStyle} value={range.from} onChange={(event) => setRange({ ...range, from: event.target.value })} /></label>
        <label style={{ display: 'grid', gap: 4 }}><span className="eyebrow">TO</span><input type="date" style={inputStyle} value={range.to} onChange={(event) => setRange({ ...range, to: event.target.value })} /></label>
        <button className="button secondary" type="submit">Export payouts CSV</button>
      </form>
    </div>
    {error && <p role="alert" className="low-confidence">{error}</p>}
    {result && <p role="status">Matched {result.matched}, mismatched {result.mismatched}, unmatched {result.unmatched.length}, invalid rows {result.invalid_rows.length}.</p>}
    <MerchantStatements api={api} tenantId={tenantId} />
  </div>;
}

export function ClaimsPanel({ api, tenantId, canDecide }: Base & { canDecide: boolean }) {
  return <StaffClaims list={(status) => api.getClaims(tenantId, status)} update={(id, input) => api.updateClaim(tenantId, id, input)} canDecide={canDecide} />;
}

function MerchantStatements({ api, tenantId }: Base) {
  const { data: merchants } = useLoad<Merchant[]>(() => api.getMerchants(tenantId), [api, tenantId]);
  const [merchantId, setMerchantId] = useState('');
  const chosen = merchantId || merchants?.[0]?.id || '';
  if (!merchants?.length) return null;
  return <div style={{ marginTop: 20 }}>
    <label style={{ display: 'grid', gap: 4, marginBottom: 8, maxWidth: 320 }}><span className="eyebrow">MERCHANT PAYOUT STATEMENT FOR</span><select style={inputStyle} value={chosen} onChange={(event) => setMerchantId(event.target.value)} aria-label="Merchant">{merchants.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
    <StatementCard key={chosen} title="Statement" load={(from, to) => api.getStatement(tenantId, chosen, from, to)} download={(from, to) => api.downloadStatement(tenantId, chosen, from, to)} />
  </div>;
}

/** Settings: members & roles, zones & rate cards, audit history. */
type SettingsTab = 'members' | 'merchants' | 'zones' | 'audit' | 'dispatch' | 'billing';

export function SettingsPanels({ api, tenantId, tenant, initialTab, onRenamed }: Base & { tenant: MyTenant | null; initialTab?: SettingsTab; onRenamed?: () => void }) {
  const [tab, setTab] = useState<SettingsTab>(initialTab ?? 'members');
  const [renaming, setRenaming] = useState(false);
  const canRename = tenant?.role === 'tenant_owner' || tenant?.role === 'tenant_admin' || tenant?.role === 'dev';
  useEffect(() => { if (initialTab) setTab(initialTab); }, [initialTab]);
  return <div>
    <div className="segmented" style={{ marginBottom: 16, display: 'inline-flex' }}>{(['members', 'merchants', 'zones', 'dispatch', 'billing', 'audit'] as const).map((t) => <button key={t} className={tab === t ? 'selected' : ''} onClick={() => setTab(t)}>{{ members: 'Members & roles', merchants: 'Merchants', zones: 'Zones & rate cards', dispatch: 'Dispatching', billing: 'Plan & billing', audit: 'Audit history' }[t]}</button>)}</div>
    <p className="muted" style={{ marginTop: 0 }}>Workspace <b>{tenant?.name}</b> · your role <b>{tenant?.role ? label(tenant.role) : '—'}</b>{canRename && <> · <button className="button secondary" style={{ minHeight: 0, padding: '4px 10px' }} onClick={() => setRenaming(true)}>Rename</button></>}</p>
    {renaming && tenant && <RenameDialog current={tenant.name} save={(name) => api.renameWorkspace(tenantId, name)} close={() => setRenaming(false)} done={() => { setRenaming(false); onRenamed?.(); }} />}
    {tab === 'members' && <Members api={api} tenantId={tenantId} />}
    {tab === 'merchants' && <Merchants api={api} tenantId={tenantId} canAdd={tenant?.role === 'tenant_owner' || tenant?.role === 'dev'} />}
    {tab === 'zones' && <Zones api={api} tenantId={tenantId} />}
    {tab === 'dispatch' && <DispatchingSettings api={api} tenantId={tenantId} canChange={tenant?.role === 'tenant_owner' || tenant?.role === 'tenant_admin' || tenant?.role === 'dev'} />}
    {tab === 'billing' && <BillingPanel api={api} tenantId={tenantId} />}
    {tab === 'audit' && <Audit api={api} tenantId={tenantId} />}
  </div>;
}

const STATUS_TEXT = { active: 'Active', ending: 'Ending soon', grace: 'Ended: renew now to keep adding work', expired: 'Ended: adding new work is paused' } as const;

function BillingPanel({ api, tenantId }: Base) {
  const { data, error, reload } = useLoad(() => api.getBilling(tenantId), [api, tenantId]);
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState('');
  // Paystack sends the person back with ?reference=...: ask the server (not the browser) whether it was paid.
  useEffect(() => {
    const reference = new URLSearchParams(window.location.search).get('reference');
    if (!reference) return;
    api.verifyPayment(tenantId, reference).then(() => { setMessage('Payment received. Your plan is now active.'); reload(); }).catch((exc) => setMessage(friendlyMessage(exc)));
    window.history.replaceState(null, '', window.location.pathname);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  async function pay(plan: string) {
    setBusy(plan);
    try { const { authorization_url } = await api.startCheckout(tenantId, plan); window.location.href = authorization_url; } catch (exc) { setMessage(friendlyMessage(exc)); setBusy(''); }
  }
  if (error) return <p role="alert" className="low-confidence">{error}</p>;
  if (!data) return <p className="muted">Loading…</p>;
  const limit = (value: number | null) => (value === null ? 'no limit' : String(value));
  const meters = [['Riders', data.usage.riders, data.plan.riders], ['Team members', data.usage.staff, data.plan.staff], ['Merchants', data.usage.merchants, data.plan.merchants], ['Orders this month', data.usage.orders, data.plan.orders_per_month]] as const;
  return <div className="card" style={{ padding: 16 }}>
    {message && <p role="status" className="notice" style={{ marginTop: 0 }}>{message}</p>}
    <div className="drawer-block"><span className="eyebrow">YOUR PLAN</span><b>{data.plan.name}</b><small>{STATUS_TEXT[data.status]}{data.valid_until ? ` · until ${when(data.valid_until)}` : ''}</small>{!data.enforced && <small className="muted">Plan limits are not being enforced yet.</small>}</div>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 12, margin: '12px 0' }}>
      {meters.map(([name, used, max]) => <div key={name} className="drawer-block"><span className="eyebrow">{name.toUpperCase()}</span><b>{used} <small className="muted">of {limit(max)}</small></b><progress value={max ? Math.min(used, max) : 0} max={max ?? 1} aria-label={name} style={{ width: '100%' }} /></div>)}
    </div>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 12 }}>
      {data.plans.filter((p) => p.key !== 'trial').map((p) => <div key={p.key} className="drawer-block" style={p.key === data.plan.key ? { outline: '2px solid var(--accent, #c9a227)', borderRadius: 12 } : undefined}>
        <b>{p.name}</b><span>{p.key === 'enterprise' ? 'Custom price' : `${money.format(p.price_ngn)} / month`}</span><small>{p.blurb}</small>
        <small>{limit(p.riders)} riders · {limit(p.staff)} team · {limit(p.merchants)} merchants · {limit(p.orders_per_month)} orders/month</small>
        {p.key === 'enterprise' ? <small className="muted">Contact RouteBridge</small> : <button className="button" disabled={!data.payments_enabled || busy !== ''} onClick={() => pay(p.key)}>{busy === p.key ? 'Opening payment…' : p.key === data.plan.key ? 'Renew' : 'Choose'}</button>}
      </div>)}
    </div>
    {!data.payments_enabled && <p className="muted">Online payment is not switched on yet. Contact RouteBridge to change your plan.</p>}
  </div>;
}

function Members({ api, tenantId }: Base) {
  const { data, error, reload } = useLoad<Member[]>(() => api.getMembers(tenantId), [api, tenantId]);
  const [formError, setFormError] = useState('');
  const [newRole, setNewRole] = useState('dispatcher');
  const merchants = useLoad<Merchant[]>(() => api.getMerchants(tenantId), [api, tenantId]);
  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    try {
      await api.addMember(tenantId, { clerk_user_id: String(form.get('clerk_user_id')).trim(), role: String(form.get('role')), full_name: String(form.get('full_name') || '') || undefined, email: String(form.get('email') || '') || undefined, merchant_id: newRole === 'merchant_user' ? String(form.get('merchant_id') || '') || undefined : undefined });
      formEl.reset(); setNewRole('dispatcher'); setFormError(''); reload();
    } catch (exc) { setFormError(friendlyMessage(exc)); }
  }
  async function change(member: Member, input: { role?: string; status?: 'active' | 'inactive' }) {
    try { await api.updateMember(tenantId, member.membership_id, input); setFormError(''); reload(); } catch (exc) { setFormError(friendlyMessage(exc)); }
  }
  return <div className="card" style={{ padding: 16 }}>
    <p className="muted" style={{ marginTop: 0 }}>Add someone only with their user id. Ask them to sign up and open RouteBridge: the screen shows their user id and a button that copies a message to send you.</p>
    <form onSubmit={add} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
      <input name="clerk_user_id" placeholder="User id (user_…)" required minLength={3} pattern="\S+" title="Paste the user id exactly as they sent it, with no spaces" autoComplete="off" style={inputStyle} aria-label="User id" />
      <input name="full_name" placeholder="Name" style={inputStyle} aria-label="Name" />
      <input name="email" type="email" placeholder="Email" style={inputStyle} aria-label="Email" />
      <select name="role" value={newRole} onChange={(event) => setNewRole(event.target.value)} style={inputStyle} aria-label="Role">{ROLES.map((r) => <option key={r} value={r}>{label(r)}</option>)}</select>
      {newRole === 'merchant_user' && <select name="merchant_id" required defaultValue="" style={inputStyle} aria-label="Works for merchant"><option value="" disabled>{merchants.data?.length ? 'Which merchant do they work for?' : 'Add a merchant first'}</option>{merchants.data?.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select>}
      <button className="button primary" type="submit">Add member</button>
    </form>
    {(error || formError) && <p role="alert" className="low-confidence">{error || formError}</p>}
    <div className="table-scroll"><table><thead><tr><th>MEMBER</th><th>ROLE</th><th>STATUS</th></tr></thead><tbody>
      {data?.length === 0 && <tr><td colSpan={3} className="muted">No members yet.</td></tr>}
      {data?.map((m) => <tr key={m.membership_id}>
        <td><b>{m.full_name ?? m.clerk_user_id}</b><small>{m.email ?? m.clerk_user_id}</small>{m.merchant_name && <small>Works for {m.merchant_name}</small>}</td>
        <td><select style={inputStyle} value={m.role} onChange={(event) => change(m, { role: event.target.value })} aria-label={`Role for ${m.full_name ?? m.clerk_user_id}`}>{ROLES.map((r) => <option key={r} value={r}>{label(r)}</option>)}</select></td>
        <td><button className="button secondary" onClick={() => change(m, { status: m.status === 'active' ? 'inactive' : 'active' })}>{m.status === 'active' ? 'Deactivate' : 'Reactivate'}</button></td>
      </tr>)}
    </tbody></table></div>
  </div>;
}

function MerchantRow({ merchant, canEdit, save, remove }: { merchant: Merchant; canEdit: boolean; save: (input: { contact_phone?: string; contact_email?: string; notify_orders?: boolean }) => Promise<void>; remove: () => Promise<void> }) {
  const [confirming, setConfirming] = useState(false);
  const [phone, setPhone] = useState(merchant.contact_phone ?? '');
  const [email, setEmail] = useState(merchant.contact_email ?? '');
  const phoneChanged = phone.trim() !== (merchant.contact_phone ?? '');
  const emailChanged = email.trim() !== (merchant.contact_email ?? '');
  const changed = phoneChanged || emailChanged;
  return <><tr>
    <td><b>{merchant.name}</b></td>
    <td>{canEdit ? <span style={{ display: 'flex', gap: 6 }}><input type="tel" value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="No number yet" aria-label={`Phone for ${merchant.name}`} style={inputStyle} /><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="No email" aria-label={`Email for ${merchant.name}`} style={inputStyle} />{changed && <button className="button secondary" onClick={() => save({ ...(phoneChanged ? { contact_phone: phone.trim() } : {}), ...(emailChanged ? { contact_email: email.trim() } : {}) })}>Save</button>}</span> : (merchant.contact_phone || <span className="muted">No number</span>)}</td>
    <td>{(merchant.contact_phone || merchant.contact_email) && canEdit && <label style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}><input type="checkbox" checked={merchant.notify_orders !== false} onChange={(event) => save({ notify_orders: event.target.checked })} />Send alerts</label>}
      {canEdit && !confirming && <button className="button secondary" style={{ marginLeft: 8 }} onClick={() => setConfirming(true)} aria-label={`Remove ${merchant.name}`}>Remove</button>}</td>
  </tr>
  {canEdit && confirming && <tr><td colSpan={3}><div role="alert" style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', padding: '4px 0' }}><span style={{ flex: '1 1 280px' }}>Remove <span style={{ fontWeight: 700 }}>{merchant.name}</span>? Its login stops working and no new orders can be created for it. Past orders and statements are kept.</span><button className="button primary" onClick={() => { setConfirming(false); remove(); }}>Yes, remove</button><button className="button secondary" onClick={() => setConfirming(false)}>Keep</button></div></td></tr>}</>;
}

function Merchants({ api, tenantId, canAdd }: Base & { canAdd: boolean }) {
  const { data, error, reload } = useLoad<Merchant[]>(() => api.getMerchants(tenantId), [api, tenantId]);
  const [formError, setFormError] = useState('');
  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    const name = String(form.get('name') ?? '').trim();
    try { await api.createMerchant(tenantId, name, String(form.get('clerk_user_id') ?? '').trim()); formEl.reset(); setFormError(''); reload(); } catch (exc) { setFormError(friendlyMessage(exc)); }
  }
  return <div className="card" style={{ padding: 16 }}>
    <p className="muted" style={{ marginTop: 0 }}>Merchants are the businesses you deliver for (a pharmacy, a shop). Every order belongs to one. Add a shop with the user id it sends you after signing up; it then fills in its own phone, address and bank account.</p>
    {canAdd ? <form onSubmit={add} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
      <input name="name" placeholder="Merchant name" required minLength={2} maxLength={200} style={inputStyle} aria-label="Merchant name" />
      <input name="clerk_user_id" placeholder="Shop's user id (user_…)" required minLength={3} pattern="\S+" title="Paste the user id exactly as the shop sent it, with no spaces" autoComplete="off" style={inputStyle} aria-label="The shop's user id" />
      <button className="button primary" type="submit">Add merchant</button>
    </form> : <p className="muted" style={{ marginBottom: 16 }}>Only the workspace owner can add merchants. Ask the owner if a business is missing from this list.</p>}
    {(error || formError) && <p role="alert" className="low-confidence">{error || formError}</p>}
    <div className="table-scroll"><table><thead><tr><th>MERCHANT</th><th>TEXTS AND EMAILS NEW ORDERS TO</th><th /></tr></thead><tbody>
      {data?.length === 0 && <tr><td colSpan={3} className="muted">{canAdd ? 'No merchants yet. Add your first one above.' : 'No merchants yet. The owner needs to add the first one.'}</td></tr>}
      {data?.map((m) => <MerchantRow key={m.id} merchant={m} canEdit={canAdd} save={async (input) => { try { await api.updateMerchant(tenantId, m.id, input); setFormError(''); reload(); } catch (exc) { setFormError(friendlyMessage(exc)); } }} remove={async () => { try { await api.removeMerchant(tenantId, m.id); setFormError(''); reload(); } catch (exc) { setFormError(friendlyMessage(exc)); } }} />)}
    </tbody></table></div>
    <MerchantDetailsPanel api={api} tenantId={tenantId} refreshKey={data?.length ?? 0} />
  </div>;
}

function Zones({ api, tenantId }: Base) {
  const zones = useLoad<Zone[]>(() => api.getZones(tenantId), [api, tenantId]);
  const cards = useLoad<RateCard[]>(() => api.getRateCards(tenantId), [api, tenantId]);
  const areas = useLoad<OperatingArea[]>(() => api.getOperatingAreas(), [api]);
  const [error, setError] = useState('');
  async function addZone(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    try {
      await api.createZone(tenantId, { operating_area_id: String(form.get('area')), code: String(form.get('code')).trim().toUpperCase(), name: String(form.get('name')).trim() });
      formEl.reset(); setError(''); zones.reload();
    } catch (exc) { setError(friendlyMessage(exc)); }
  }
  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    try {
      await api.createRateCard(tenantId, { service_zone_id: String(form.get('zone')), name: String(form.get('name')).trim(), base_amount: String(form.get('base_amount')) });
      formEl.reset(); setError(''); cards.reload();
    } catch (exc) { setError(friendlyMessage(exc)); }
  }
  const zoneName = (id: string) => zones.data?.find((z) => z.id === id)?.name ?? id.slice(0, 8);
  return <div className="card" style={{ padding: 16 }}>
    <b>Service zones</b>
    <form onSubmit={addZone} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '10px 0' }}>
      <select name="area" required style={inputStyle} aria-label="City">{areas.data?.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select>
      <input name="code" placeholder="Code (e.g. IKJ)" required minLength={2} maxLength={50} style={inputStyle} aria-label="Zone code" />
      <input name="name" placeholder="Zone name (e.g. Ikeja)" required minLength={2} maxLength={120} style={inputStyle} aria-label="Zone name" />
      <button className="button primary" type="submit">Add zone</button>
    </form>
    <p className="muted" style={{ marginTop: 4 }}>{zones.data?.length ? zones.data.map((z) => `${z.name} (${z.code})`).join(' · ') : 'No zones yet.'}</p>
    <b>Rate cards</b>
    {!!zones.data?.length && <form onSubmit={add} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '10px 0' }}>
      <select name="zone" required style={inputStyle} aria-label="Zone">{zones.data.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}</select>
      <input name="name" placeholder="Rate card name" required maxLength={120} style={inputStyle} aria-label="Rate card name" />
      <input name="base_amount" type="number" min="0" step="0.01" placeholder="Base amount (NGN)" required style={inputStyle} aria-label="Base amount" />
      <button className="button primary" type="submit">Add rate card</button>
    </form>}
    {(error || zones.error || cards.error) && <p role="alert" className="low-confidence">{error || zones.error || cards.error}</p>}
    <div className="table-scroll"><table><thead><tr><th>ZONE</th><th>NAME</th><th>BASE</th></tr></thead><tbody>
      {cards.data?.length === 0 && <tr><td colSpan={3} className="muted">No rate cards yet.</td></tr>}
      {cards.data?.map((c) => <tr key={c.id}><td>{zoneName(c.service_zone_id)}</td><td>{c.name}</td><td>{money.format(Number(c.base_amount))}</td></tr>)}
    </tbody></table></div>
  </div>;
}

function Audit({ api, tenantId }: Base) {
  const { data, error } = useLoad<AuditRow[]>(() => api.getAudit(tenantId, 100), [api, tenantId]);
  return <div className="card" style={{ padding: 16 }}>
    {error && <p role="alert" className="low-confidence">{error}</p>}
    <div className="table-scroll"><table><thead><tr><th>WHEN</th><th>EVENT</th><th>OBJECT</th><th>ACTOR</th></tr></thead><tbody>
      {data?.length === 0 && <tr><td colSpan={4} className="muted">No activity recorded yet.</td></tr>}
      {data?.map((row) => <tr key={row.id}><td>{when(row.occurred_at)}</td><td><b>{row.event_type}</b></td><td>{row.aggregate_type} <small>{row.aggregate_id.slice(0, 8)}</small></td><td>{row.actor_type}</td></tr>)}
    </tbody></table></div>
  </div>;
}


/** Settings > Dispatching: should new orders be given to the nearest available driver automatically? */
function DispatchingSettings({ api, tenantId, canChange }: Base & { canChange: boolean }) {
  const { data, error, reload } = useLoad<{ auto_assign: boolean }>(() => api.getDispatchSettings(tenantId), [api, tenantId]);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState('');
  async function toggle() {
    if (!data) return;
    setBusy(true); setProblem('');
    try { await api.setDispatchSettings(tenantId, !data.auto_assign); await reload(); } catch (exc) { setProblem(friendlyMessage(exc)); } finally { setBusy(false); }
  }
  return <div className="card" style={{ padding: 20, maxWidth: 760 }}>
    <h3 style={{ marginTop: 0 }}>Assign new orders automatically</h3>
    <p className="muted">When this is on, every new order goes straight to the nearest free rider, the moment it is created (from the console, the merchant portal or a shop&apos;s online store). It is off by default, so nothing changes until you switch it on.</p>
    <ul className="muted" style={{ lineHeight: 1.7 }}>
      <li>Only riders who are <b>available</b> are considered. A rider who is busy or offline is skipped.</li>
      <li>The rider must be within 15 km of the drop-off. If nobody is that close, the order waits for you to choose.</li>
      <li>If the address has no map position yet, the rider who has been free the longest gets it, so work is shared fairly.</li>
      <li>You can always assign by hand, and you can press <b>Assign nearest driver</b> on any waiting order, or <b>Assign all waiting jobs</b> on the dispatch board.</li>
    </ul>
    {(error || problem) && <p role="alert" className="low-confidence">{error || problem}</p>}
    <button className={data?.auto_assign ? 'button secondary' : 'button primary'} disabled={!canChange || busy || !data} onClick={toggle}>{data?.auto_assign ? 'Turn automatic assignment off' : 'Turn automatic assignment on'}</button>
    <p style={{ marginTop: 12 }}>Right now: <b>{data ? (data.auto_assign ? 'On' : 'Off') : '…'}</b>{!canChange && ' (only the owner or an admin can change this)'}</p>
  </div>;
}
