'use client';

import { useCallback, useEffect, useState } from 'react';
import { friendlyMessage, type ApiClient, type ShopBilling } from '../lib/api';

const money = new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN', maximumFractionDigits: 0 });
const when = (iso: string | null) => (iso ? new Date(iso.endsWith('Z') || /[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`).toLocaleDateString('en-NG', { day: 'numeric', month: 'short', year: 'numeric' }) : '');
const STATUS_TEXT = { active: 'Active', ending: 'Ending soon: renew to keep sending orders', expired: 'Ended: you cannot place new orders until you pay' } as const;

/** A shop's own plan: what it is on, the plans to choose from, and paying online (Paystack). Shown on the shop's page only. */
export function ShopBillingPage({ api, tenantId }: { api: ApiClient; tenantId: string }) {
  const [data, setData] = useState<ShopBilling | null>(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState('');
  const [email, setEmail] = useState('');
  const load = useCallback(() => { api.portal.billing(tenantId).then((value) => { setData(value); setError(''); }).catch((exc) => setError(friendlyMessage(exc))); }, [api, tenantId]);
  useEffect(() => {
    // Paystack sends the shop back with ?reference=...: ask the server (never the browser) whether it was paid.
    const reference = new URLSearchParams(window.location.search).get('reference');
    if (reference) {
      window.history.replaceState(null, '', window.location.pathname);
      api.portal.verifyPayment(tenantId, reference).then((value) => { setData(value); setMessage(value.payments.find((p) => p.reference === reference)?.status === 'success' ? 'Payment received. Your plan is now active.' : 'That payment was not completed. You have not been charged for a plan.'); }).catch((exc) => { setMessage(friendlyMessage(exc)); load(); });
    } else load();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  async function pay(plan: string) {
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())) { setMessage('Enter your email address first: the payment page sends your receipt there.'); return; }
    setBusy(plan);
    try { const { authorization_url } = await api.portal.startCheckout(tenantId, plan, email.trim()); window.location.href = authorization_url; } catch (exc) { setMessage(friendlyMessage(exc)); setBusy(''); }
  }
  if (error) return <p role="alert" className="low-confidence">{error}</p>;
  if (!data) return <p className="muted">Loading your plan…</p>;
  const limit = data.plan.orders_per_month;
  return <div className="card" style={{ padding: 16 }}>
    {message && <p role="status" className="notice" style={{ marginTop: 0 }}>{message}</p>}
    {data.status === 'expired' && <p role="alert" className="low-confidence" style={{ marginTop: 0 }}>Your plan has ended. {data.payments_enabled ? 'Choose a plan below and pay online to place new orders again.' : 'Online payment is not switched on yet. Contact RouteBridge.'} Deliveries already on the road are not affected.</p>}
    <div className="drawer-block"><span className="eyebrow">YOUR PLAN</span><b>{data.plan.name}</b><small>{STATUS_TEXT[data.status]}{data.valid_until ? ` · until ${when(data.valid_until)}` : ''}{data.days_left !== null && data.status !== 'expired' ? ` (${data.days_left} day${data.days_left === 1 ? '' : 's'} left)` : ''}</small>{!data.enforced && <small className="muted">Payment is not required yet: you can keep placing orders.</small>}</div>
    <div className="drawer-block" style={{ margin: '12px 0' }}><span className="eyebrow">ORDERS THIS MONTH</span><b>{data.orders_this_month} <small className="muted">of {limit === null ? 'no limit' : limit}</small></b><progress value={limit ? Math.min(data.orders_this_month, limit) : 0} max={limit ?? 1} style={{ width: '100%' }} /></div>
    <label style={{ display: 'grid', gap: 4, margin: '4px 0 12px', maxWidth: 380 }}><span className="eyebrow">EMAIL FOR YOUR PAYMENT RECEIPT</span><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@yourshop.com" autoComplete="email" aria-label="Receipt email" style={{ padding: '8px 10px', borderRadius: 8, border: '1px solid var(--line, #d0d5dd)', background: 'transparent', color: 'inherit', font: 'inherit' }} /></label>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 12 }}>
      {data.plans.filter((p) => p.key !== 'trial').map((p) => <div key={p.key} className="drawer-block" style={p.key === data.plan.key ? { outline: '2px solid var(--accent, #c9a227)', borderRadius: 12 } : undefined}>
        <b>{p.name}</b><span>{money.format(p.price_ngn)} / month</span><small>{p.blurb}</small><small>{p.orders_per_month === null ? 'No limit' : p.orders_per_month} orders a month</small>
        <button className="button" disabled={!data.payments_enabled || busy !== ''} onClick={() => pay(p.key)}>{busy === p.key ? 'Opening payment…' : p.key === data.plan.key && data.status !== 'expired' ? 'Renew online' : 'Pay online'}</button>
      </div>)}
    </div>
    {!data.payments_enabled && <p className="muted">Online payment is not switched on yet. Contact RouteBridge.</p>}
    {data.payments.length > 0 && <><h3 style={{ marginBottom: 6 }}>Your payments</h3><div className="table-wrap"><table className="job-table"><thead><tr><th>Date</th><th>Plan</th><th>Amount</th><th>Status</th></tr></thead><tbody>{data.payments.map((p) => <tr key={p.reference}><td>{when(p.paid_at ?? p.created_at)}</td><td>{p.plan}</td><td>{money.format(p.amount_ngn)}</td><td>{p.status === 'success' ? 'Paid' : p.status === 'failed' ? 'Failed' : 'Not completed'}</td></tr>)}</tbody></table></div></>}
  </div>;
}
