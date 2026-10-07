'use client';

import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import { friendlyMessage, type ApiClient, type MyTenant, type PortalMe, type PortalOrder, type PortalSummary } from '../lib/api';
import { PortalClaims } from './claims-views';
import { StatementCard } from './statement-card';
import { ThemeToggle } from './theme-toggle';

const money = new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN', maximumFractionDigits: 0 });
const amount = (value: string) => money.format(Number(value));
const PAGES = [['Overview', '/'], ['My orders', '/orders'], ['Statements', '/statements'], ['Problems', '/problems']] as const;

// What a shop's customer-facing status is called, and how far along the road the parcel is (0 = problem).
const STATUS: Record<string, { label: string; step: number; tone: 'amber' | 'blue' | 'violet' | 'green' | 'red' }> = {
  pending: { label: 'Waiting for a rider', step: 1, tone: 'amber' },
  assigned: { label: 'Rider assigned', step: 2, tone: 'blue' },
  accepted: { label: 'Rider assigned', step: 2, tone: 'blue' },
  en_route: { label: 'On the way', step: 3, tone: 'blue' },
  arrived: { label: 'Rider has arrived', step: 4, tone: 'violet' },
  delivered: { label: 'Delivered', step: 5, tone: 'green' },
  failed_attempt: { label: 'Delivery failed', step: 0, tone: 'red' },
  rescheduled: { label: 'Rescheduled', step: 0, tone: 'amber' },
  returned: { label: 'Returned to you', step: 0, tone: 'red' },
  cancelled: { label: 'Cancelled', step: 0, tone: 'red' },
};
const statusOf = (value: string) => STATUS[value] ?? { label: value.replace(/_/g, ' '), step: 1, tone: 'blue' as const };

function greeting(date: Date) { const h = date.getHours(); return h >= 5 && h < 12 ? 'Good morning' : h >= 12 && h < 17 ? 'Good afternoon' : 'Good evening'; }
const pageFromPath = (path: string) => { const clean = path.replace(/\/+$/, ''); return clean === '/orders' ? 'My orders' : clean === '/statements' ? 'Statements' : clean === '/problems' ? 'Problems' : 'Overview'; };

function Track({ status }: { status: string }) {
  const info = statusOf(status);
  return <span className={`track track-${info.tone}`} role="img" aria-label={info.label}>
    <span className="track-road" aria-hidden="true">{[1, 2, 3, 4, 5].map((n) => <i key={n} className={info.step === 0 ? (n === 1 ? 'on' : '') : n <= info.step ? 'on' : ''} />)}</span>
    <span className="track-label">{info.label}</span>
  </span>;
}

/** The merchant portal: a shop's own staff see and create only their own shop's orders. */
export function MerchantPortal({ api, tenant, firstName, accountMenu }: { api: ApiClient; tenant: MyTenant; firstName: string; accountMenu?: ReactNode }) {
  const tenantId = tenant.tenant_id;
  const [page, setPage] = useState('Overview');
  const [me, setMe] = useState<PortalMe | null>(null);
  const [orders, setOrders] = useState<PortalOrder[] | null>(null);
  const [summary, setSummary] = useState<PortalSummary | null>(null);
  const [error, setError] = useState('');
  const [now, setNow] = useState(() => new Date());
  const [query, setQuery] = useState('');
  const [showNew, setShowNew] = useState(false);
  const [open, setOpen] = useState<PortalOrder | null>(null);
  const [justCreated, setJustCreated] = useState('');

  const load = useCallback(async () => {
    try {
      const [mine, list, totals] = await Promise.all([api.portal.me(tenantId), api.portal.orders(tenantId), api.portal.summary(tenantId)]);
      setMe(mine); setOrders(list); setSummary(totals); setError('');
    } catch (exc) { setError(friendlyMessage(exc)); }
  }, [api, tenantId]);

  useEffect(() => { load(); const timer = setInterval(load, 30_000); return () => clearInterval(timer); }, [load]);
  useEffect(() => { const timer = setInterval(() => setNow(new Date()), 60_000); return () => clearInterval(timer); }, []);
  useEffect(() => {
    const sync = () => setPage(pageFromPath(window.location.pathname));
    sync();
    window.addEventListener('popstate', sync);
    return () => window.removeEventListener('popstate', sync);
  }, []);
  useEffect(() => { document.title = `${page === 'Overview' ? 'Home' : page} | ${me?.merchant_name ?? 'Merchant'} on RouteBridge`; }, [page, me]);

  const go = (target: string) => {
    const href = PAGES.find(([label]) => label === target)?.[1] ?? '/';
    if (window.location.pathname !== href) window.history.pushState(null, '', href);
    setPage(target); window.scrollTo(0, 0);
  };
  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (orders ?? []).filter((o) => !needle || [o.external_ref, o.customer_name, o.address_text, statusOf(o.status).label].some((v) => String(v ?? '').toLowerCase().includes(needle)));
  }, [orders, query]);

  const merchantName = me?.merchant_name ?? tenant.merchant_name ?? 'your shop';
  const rows = page === 'Overview' ? shown.slice(0, 5) : shown;

  return <main className="app-shell portal">
    <header className="portal-top">
      <div className="portal-brand"><span className="brand-mark" role="img" aria-label="RouteBridge logo" /><div><strong>{merchantName}</strong><small>Delivering with {me?.workspace_name ?? tenant.name}</small></div></div>
      <nav className="portal-nav" aria-label="Portal">{PAGES.map(([label, href]) => <a key={label} href={href} aria-current={page === label ? 'page' : undefined} className={page === label ? 'active' : ''} onClick={(event) => { event.preventDefault(); go(label); }}>{label}</a>)}</nav>
      <div className="portal-actions"><ThemeToggle /><button className="button primary" onClick={() => setShowNew(true)}>+ New order</button>{accountMenu}</div>
    </header>

    <div className="page-wrap">
      {page === 'Overview' && <section className="hero" aria-label="Welcome">
        <div className="hero-copy">
          <span className="hero-date">{now.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}</span>
          <h1>{greeting(now)}{firstName ? `, ${firstName}` : ''}</h1>
          <p className="hero-welcome">Welcome to the {merchantName} portal.</p>
          <p className="hero-sub">{summary ? (summary.in_progress ? `${summary.in_progress} of your parcels ${summary.in_progress === 1 ? 'is' : 'are'} on the way to customers right now.` : 'Nothing is on the road at the moment. Send a new order and we will take it from there.') : 'Loading your deliveries…'}</p>
          <div className="hero-actions"><button className="hero-btn solid" onClick={() => setShowNew(true)}>+ New order</button><button className="hero-btn ghost" onClick={() => go('My orders')}>See all my orders</button></div>
        </div>
        <div className="hero-art" aria-hidden="true">
          <svg viewBox="0 0 420 240"><path className="hero-route" d="M20 200 C110 70 180 210 250 120 S370 40 400 30" /><circle className="hero-dot" r="7"><animateMotion dur="9s" repeatCount="indefinite" path="M20 200 C110 70 180 210 250 120 S370 40 400 30" /></circle><circle cx="20" cy="200" r="9" className="hero-pin a" /><circle cx="250" cy="120" r="9" className="hero-pin b" /><circle cx="400" cy="30" r="11" className="hero-pin c" /></svg>
          <div className="hero-chip one"><b>{summary?.delivered ?? 0}</b><span>delivered</span></div>
          <div className="hero-chip two"><b>{summary?.orders_total ?? 0}</b><span>orders in total</span></div>
        </div>
      </section>}

      {page === 'Statements' && <><div className="page-heading"><div><div className="breadcrumb">{merchantName.toUpperCase()}</div><h1>Statements</h1><p>What was delivered, the cash collected from your customers, the delivery fees, and what is left to pay you.</p></div></div><StatementCard load={(from, to) => api.portal.statement(tenantId, from, to)} download={(from, to) => api.portal.downloadStatement(tenantId, from, to)} /></>}
      {page === 'Problems' && <><div className="page-heading"><div><div className="breadcrumb">{merchantName.toUpperCase()}</div><h1>Problems</h1><p>Damaged or lost goods, refunds and disputes. Tell us what happened and follow the answer here.</p></div></div><PortalClaims list={() => api.portal.claims(tenantId)} open={(input) => api.portal.openClaim(tenantId, input)} orders={orders ?? []} /></>}
      {page === 'My orders' && <div className="page-heading"><div><div className="breadcrumb">{merchantName.toUpperCase()}</div><h1>My orders</h1><p>Every parcel you have sent with {me?.workspace_name ?? tenant.name}, and where it is now.</p></div></div>}

      {error && <div className="notice" role="alert"><span className="notice-icon">!</span><div><b>We could not load your orders</b><span>{error}</span></div><button onClick={load}>Try again</button></div>}
      {justCreated && <div className="notice" role="status"><span className="notice-icon">✓</span><div><b>Order {justCreated} sent</b><span>A rider will be assigned shortly. You can follow it here.</span></div><button onClick={() => setJustCreated('')}>Dismiss</button></div>}

      {page === 'Overview' && <div className="needs-action portal-tiles" aria-label="Your numbers">
        {([[summary?.in_progress ?? 0, 'on the way', 'tone-blue', true], [summary?.delivered ?? 0, 'delivered', 'tone-green', true], [summary?.problems ?? 0, 'need attention', 'tone-red', (summary?.problems ?? 0) > 0], [summary ? amount(summary.cod_to_collect) : '₦0', 'cash still to collect', 'tone-amber', true]] as [number | string, string, string, boolean][])
          .map(([value, text, tone, hot]) => <div key={text} className={`action-tile ${tone}${hot ? ' hot' : ''}`}><b>{value}</b><span>{text}</span></div>)}
      </div>}
      {page === 'Overview' && summary && <p className="muted" style={{ marginTop: -8, marginBottom: 24 }}>Cash collected from your customers so far: <b>{amount(summary.cod_collected)}</b>. Payouts are handled by {me?.workspace_name ?? tenant.name}.</p>}

      <div className="section-head"><div><h2>{page === 'Overview' ? 'Latest orders' : 'All orders'}</h2><p>{page === 'Overview' ? 'Your five most recent parcels' : `${shown.length} order${shown.length === 1 ? '' : 's'}`}</p></div>
        {page === 'My orders' && <input className="topbar-search" style={{ display: 'block' }} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by order, customer or address" aria-label="Search your orders" />}</div>
      <div className="card job-table"><div className="table-scroll"><table><thead><tr><th>ORDER</th><th>CUSTOMER</th><th>ADDRESS</th><th>STATUS</th><th>COD</th></tr></thead><tbody>
        {orders === null && !error && [0, 1, 2].map((n) => <tr key={n} aria-hidden="true"><td colSpan={5}><div className="skeleton" /></td></tr>)}
        {orders !== null && !rows.length && <tr><td colSpan={5} className="muted">{orders.length ? 'Nothing matches that search.' : 'No orders yet. Press “New order” to send your first parcel.'}</td></tr>}
        {rows.map((o) => <tr key={o.id} tabIndex={0} onClick={() => setOpen(o)} onKeyDown={(event) => { if (event.key === 'Enter') setOpen(o); }}>
          <td><b className="order-id">{o.external_ref}</b><small>{new Date(o.created_at.endsWith('Z') ? o.created_at : `${o.created_at}Z`).toLocaleString('en-NG', { dateStyle: 'medium', timeStyle: 'short' })}</small></td>
          <td><b>{o.customer_name}</b></td><td><b>{o.address_text}</b>{o.landmark && <small>{o.landmark}</small>}</td>
          <td><Track status={o.status} /></td><td><b>{amount(o.cod_amount)}</b></td></tr>)}
      </tbody></table></div>
        {page === 'Overview' && (orders?.length ?? 0) > 5 && <div className="table-footer"><span>Showing 5 of {orders?.length}</span><button onClick={() => go('My orders')}>View all orders →</button></div>}
      </div>
    </div>

    {open && <OrderDrawer order={open} close={() => setOpen(null)} />}
    {showNew && <NewOrder api={api} tenantId={tenantId} close={() => setShowNew(false)} created={(ref) => { setShowNew(false); setJustCreated(ref); load(); go('My orders'); }} />}
  </main>;
}

function OrderDrawer({ order, close }: { order: PortalOrder; close: () => void }) {
  const [copied, setCopied] = useState(false);
  const link = order.tracking_token ? `${window.location.origin}/track/${order.tracking_token}` : '';
  return <div className="drawer-backdrop" onClick={close}><aside className="drawer" onClick={(event) => event.stopPropagation()}>
    <button className="close" onClick={close} aria-label="Close">×</button>
    <span className="eyebrow">ORDER</span><h2>{order.external_ref}</h2>
    <Track status={order.status} />
    <div className="drawer-block"><span className="eyebrow">CUSTOMER</span><b>{order.customer_name}</b><small>{order.address_text}</small>{order.landmark && <small>{order.landmark}</small>}</div>
    <div className="drawer-block"><span className="eyebrow">PAYMENT</span><div className="payment-row"><b>{amount(order.cod_amount)}</b><span>to collect on delivery</span></div><small>Order value {amount(order.total_amount)}</small></div>
    <div className="drawer-block"><span className="eyebrow">RIDER</span><b>{order.rider_assigned ? 'A rider has been assigned' : 'No rider yet'}</b></div>
    {link && <div className="drawer-block"><span className="eyebrow">TRACKING LINK FOR YOUR CUSTOMER</span><small style={{ wordBreak: 'break-all' }}>{link}</small>
      <button className="button secondary" onClick={async () => { try { await navigator.clipboard.writeText(link); setCopied(true); } catch { setCopied(false); } }}>{copied ? 'Link copied' : 'Copy link'}</button></div>}
    <div className="drawer-actions"><button className="button secondary" onClick={close}>Close</button></div>
  </aside></div>;
}

const field = { padding: '12px 14px', borderRadius: 12, border: '1.5px solid var(--line)', background: 'transparent', color: 'inherit', font: 'inherit', width: '100%', boxSizing: 'border-box' } as const;

function NewOrder({ api, tenantId, close, created }: { api: ApiClient; tenantId: string; close: () => void; created: (ref: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [key] = useState(() => crypto.randomUUID());
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const get = (name: string) => String(form.get(name) ?? '').trim();
    setBusy(true); setError('');
    try {
      const order = await api.portal.createOrder(tenantId, {
        customer_name: get('customer_name'), customer_phone: get('customer_phone'), address_text: get('address_text'),
        landmark: get('landmark') || undefined, delivery_notes: get('delivery_notes') || undefined, external_ref: get('external_ref') || undefined,
        total_amount: get('total_amount') || '0', cod_amount: get('cod_amount') || '0',
      }, key);
      created(order.external_ref);
    } catch (exc) { setError(friendlyMessage(exc)); setBusy(false); }
  }
  const labelled = (text: string, name: string, extra: Record<string, unknown> = {}) => <label style={{ display: 'grid', gap: 6, marginBottom: 14 }}><span className="eyebrow">{text}</span><input name={name} style={field} {...extra} /></label>;
  return <div className="drawer-backdrop" onClick={close}><aside className="drawer" onClick={(event) => event.stopPropagation()}>
    <button className="close" onClick={close} aria-label="Close">×</button>
    <h2>New order</h2>
    <p className="muted">Tell us who to deliver to. We take it from here.</p>
    <form onSubmit={submit}>
      {labelled('Customer name', 'customer_name', { required: true, maxLength: 200, autoFocus: true })}
      {labelled('Customer phone', 'customer_phone', { required: true, minLength: 5, maxLength: 30, inputMode: 'tel', placeholder: '+234…' })}
      {labelled('Delivery address', 'address_text', { required: true, maxLength: 500 })}
      {labelled('Landmark (helps the rider)', 'landmark', { maxLength: 300, placeholder: 'e.g. Opposite the yellow supermarket sign' })}
      {labelled('Cash to collect (₦)', 'cod_amount', { type: 'number', min: 0, step: '0.01', defaultValue: '0' })}
      {labelled('Order value (₦)', 'total_amount', { type: 'number', min: 0, step: '0.01', defaultValue: '0' })}
      {labelled('Your order number (optional)', 'external_ref', { maxLength: 100, placeholder: 'We make one if you leave this empty' })}
      {labelled('Notes for the rider (optional)', 'delivery_notes', { maxLength: 1000 })}
      {error && <p role="alert" className="low-confidence">{error}</p>}
      <div className="drawer-actions"><button type="button" className="button secondary" onClick={close}>Cancel</button><button type="submit" className="button primary" disabled={busy}>{busy ? 'Sending…' : 'Send order'}</button></div>
    </form>
  </aside></div>;
}
