'use client';

import { useCallback, useEffect, useState } from 'react';
import { friendlyMessage, type ApiClient, type DeliveryCodeRequest } from '../lib/api';
import { callLink, smsLink, whatsappLink } from '../lib/phone-links';

const spaced = (code: string) => code.replace(/(\d{3})(\d{3})/, '$1 $2');

/**
 * A rider has reached a customer and asked for a delivery code. With no SMS sender, a person here passes it on (WhatsApp, a text from their own
 * phone, or a call) and presses "Mark as sent". Shows nothing when no one is waiting, and nothing to roles that may not see codes.
 */
export function DeliveryCodePanel({ api, tenantId, refreshKey, onCount }: { api: ApiClient; tenantId: string; refreshKey: number; onCount: (count: number) => void }) {
  const [items, setItems] = useState<DeliveryCodeRequest[]>([]);
  const [busy, setBusy] = useState('');
  const [copied, setCopied] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(() => api.getDeliveryCodes(tenantId).then((rows) => { setItems(rows); onCount(rows.length); }).catch(() => { setItems([]); onCount(0); }), [api, tenantId, onCount]);
  useEffect(() => { load(); }, [load, refreshKey]);
  useEffect(() => { const timer = setInterval(load, 15000); return () => clearInterval(timer); }, [load]);

  async function sent(item: DeliveryCodeRequest) {
    setBusy(item.id); setError('');
    try { await api.markDeliveryCodeSent(tenantId, item.id); await load(); } catch (exc) { setError(friendlyMessage(exc)); } finally { setBusy(''); }
  }
  async function copy(item: DeliveryCodeRequest) {
    try { await navigator.clipboard.writeText(item.message); setCopied(item.id); setTimeout(() => setCopied(''), 2500); } catch { setError('Copying is blocked in this browser. Select the message and copy it by hand.'); }
  }

  if (items.length === 0) return null;
  return <section aria-label="Delivery codes to send" role="alert" className="card" style={{ padding: 18, marginBottom: 20, borderLeft: '6px solid #ff7a29', background: 'linear-gradient(90deg,#fff4ea,#fff 40%)' }}>
    <b style={{ fontSize: 18 }}>🔔 {items.length === 1 ? 'A rider is waiting for a delivery code' : `${items.length} riders are waiting for a delivery code`}</b>
    <p className="muted" style={{ margin: '4px 0 14px' }}>Send each code to the customer now (WhatsApp, a text from your phone, or a call), then press <b>Mark as sent</b>. The customer gives the code to the rider at the door.</p>
    {error && <p role="alert" className="low-confidence">{error}</p>}
    <div style={{ display: 'grid', gap: 12 }}>
      {items.map((item) => <div key={item.id} style={{ border: '1px solid #f3d3bb', borderRadius: 14, padding: 14, background: '#fff', display: 'grid', gap: 10 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <div>
            <b>Order {item.order_ref ?? ''}</b> · {item.customer_name ?? 'Customer'}<br />
            <small className="muted">{item.customer_phone ?? 'no phone on file'}{item.driver_name ? ` · rider ${item.driver_name}` : ''} · valid for {item.minutes_left} more min</small>
          </div>
          <div aria-label="Delivery code" style={{ font: '800 32px/1 ui-monospace, Menlo, Consolas, monospace', letterSpacing: 4, color: '#0f2744', background: '#eef3f8', borderRadius: 12, padding: '10px 16px' }}>{spaced(item.code)}</div>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {item.customer_phone && <>
            <a className="button secondary" href={whatsappLink(item.customer_phone, item.message)} target="_blank" rel="noreferrer">WhatsApp</a>
            <a className="button secondary" href={smsLink(item.customer_phone, item.message)}>Text message</a>
            <a className="button secondary" href={callLink(item.customer_phone)}>Call</a>
          </>}
          <button className="button secondary" onClick={() => copy(item)}>{copied === item.id ? 'Copied ✓' : 'Copy message'}</button>
          <button className="button primary" disabled={busy === item.id} onClick={() => sent(item)}>{busy === item.id ? 'Saving…' : 'Mark as sent'}</button>
        </div>
      </div>)}
    </div>
  </section>;
}
