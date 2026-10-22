'use client';

import { useState } from 'react';
import { friendlyMessage, type ApiClient, type JoinRequest } from '../lib/api';

/**
 * People who signed up and pressed "Send to the Admin". The Admin adds them in one press (a shop by its id; a rider as Staff or
 * Contracted), or dismisses the request. Added people drop off the list by themselves.
 */
export function JoinRequestsPanel({ api, tenantId, rows, canAdd, onChanged }: { api: ApiClient; tenantId: string; rows: JoinRequest[]; canAdd: boolean; onChanged: () => void }) {
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);
  if (!rows.length) return null;
  async function run(id: string, action: () => Promise<unknown>, done: string) {
    setBusy(id); setMessage(null);
    try { await action(); setMessage({ text: done, ok: true }); onChanged(); } catch (exc) { setMessage({ text: friendlyMessage(exc), ok: false }); } finally { setBusy(''); }
  }
  const copy = (text: string) => { void navigator.clipboard?.writeText(text).then(() => setMessage({ text: 'ID copied.', ok: true }), () => undefined); };
  return <section className="card join-requests" aria-labelledby="join-requests-title">
    <div className="join-requests-head">
      <span className="join-requests-badge" aria-hidden="true">{rows.length}</span>
      <div><h2 id="join-requests-title">Waiting to join</h2><p>{rows.length === 1 ? 'Someone has' : `${rows.length} people have`} signed up and sent you their ID. Add them here.</p></div>
    </div>
    {message && <p role="status" className={message.ok ? 'join-requests-ok' : 'low-confidence'}>{message.text}</p>}
    <ul className="join-requests-list">
      {rows.map((row) => {
        const shop = row.role === 'merchant_user';
        const title = (shop ? row.shop_name : null) || row.full_name || row.email || 'New sign-up';
        return <li key={row.id}>
          <div className="join-requests-who">
            <span className={`join-requests-role ${shop ? 'is-shop' : 'is-driver'}`}>{shop ? 'Shop' : 'Driver'}</span>
            <b>{title}</b>
            <small>{[shop && row.shop_name ? row.full_name : null, row.phone, row.email, row.place].filter(Boolean).join(' · ')}</small>
            {!shop && row.zones.length > 0 && <small>Delivers in: {row.zones.join(', ')}</small>}
            <small>Sent {new Date(row.sent_at).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })} · ID <code>{row.clerk_user_id}</code> <button type="button" className="link-button" onClick={() => copy(row.clerk_user_id)}>Copy</button></small>
          </div>
          {canAdd && <div className="join-requests-actions">
            {shop
              ? <button className="button primary" disabled={!!busy} onClick={() => run(row.id, () => api.createMerchant(tenantId, row.shop_name ?? '', row.clerk_user_id), `${title} was added. They can now register their shop.`)}>Add shop</button>
              : <>
                <button className="button primary" disabled={!!busy} onClick={() => run(row.id, () => api.addMember(tenantId, { clerk_user_id: row.clerk_user_id, role: 'driver', fleet_type: 'staff' }), `${title} was added as a Staff driver.`)}>Add as Staff</button>
                <button className="button primary" disabled={!!busy} onClick={() => run(row.id, () => api.addMember(tenantId, { clerk_user_id: row.clerk_user_id, role: 'driver', fleet_type: 'contracted' }), `${title} was added as a Contracted driver.`)}>Add as Contracted</button>
              </>}
            <button className="button secondary" disabled={!!busy} onClick={() => { if (window.confirm(`Dismiss the request from ${title}? They can send it again.`)) run(row.id, () => api.dismissJoinRequest(tenantId, row.id), 'Request dismissed.'); }}>Dismiss</button>
          </div>}
        </li>;
      })}
    </ul>
  </section>;
}
