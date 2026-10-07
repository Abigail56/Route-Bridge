'use client';

import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { friendlyMessage, type Claim, type PortalOrder } from '../lib/api';

const money = new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN', maximumFractionDigits: 0 });
const inputStyle = { padding: '8px 10px', borderRadius: 8, border: '1px solid var(--line, #d0d5dd)', background: 'transparent', color: 'inherit', font: 'inherit' } as const;
const KINDS: Record<string, string> = { dispute: 'Dispute', refund: 'Refund', damage: 'Damaged goods', loss: 'Lost parcel' };
const STATUS: Record<string, string> = { open: 'Received', investigating: 'Being looked into', approved: 'Approved', rejected: 'Not approved', paid: 'Paid' };
const asDate = (iso: string) => new Date(iso.endsWith('Z') || /[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`).toLocaleDateString('en-NG');

function useClaims(load: () => Promise<Claim[]>) {
  const [claims, setClaims] = useState<Claim[] | null>(null);
  const [error, setError] = useState('');
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const reload = useCallback(() => load().then((rows) => { setClaims(rows); setError(''); }).catch((exc) => setError(friendlyMessage(exc))), []);
  useEffect(() => { reload(); }, [reload]);
  return { claims, error, reload };
}

/** The shop's side: report a problem with a delivery and follow what the company decided. */
export function PortalClaims({ list, open, orders }: { list: () => Promise<Claim[]>; open: (input: { kind: string; description: string; amount_claimed: string; order_id?: string }) => Promise<Claim>; orders: PortalOrder[] }) {
  const { claims, error, reload } = useClaims(list);
  const [formError, setFormError] = useState('');
  const [sent, setSent] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    try {
      await open({ kind: String(data.get('kind')), description: String(data.get('description')).trim(), amount_claimed: String(data.get('amount') || '0'), order_id: String(data.get('order') || '') || undefined });
      form.reset(); setFormError(''); setSent(true); reload();
    } catch (exc) { setFormError(friendlyMessage(exc)); setSent(false); }
  }
  return <div style={{ display: 'grid', gap: 16 }}>
    <form className="card" style={{ padding: 16, display: 'grid', gap: 10 }} onSubmit={submit}>
      <b>Report a problem</b>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <select name="kind" style={inputStyle} aria-label="What happened" defaultValue="damage">{Object.entries(KINDS).map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select>
        <select name="order" style={inputStyle} aria-label="Which order" defaultValue=""><option value="">Not about one order</option>{orders.slice(0, 100).map((o) => <option key={o.id} value={o.id}>{o.external_ref} · {o.customer_name ?? ''}</option>)}</select>
        <input name="amount" type="number" min="0" step="1" placeholder="Amount you are claiming (₦)" style={inputStyle} aria-label="Amount claimed" />
      </div>
      <textarea name="description" required minLength={5} maxLength={2000} rows={3} placeholder="Tell us what happened" style={inputStyle} aria-label="What happened, in your words" />
      <div><button className="button primary" type="submit">Send to {`the company`}</button></div>
      {sent && <p role="status">Sent. You can follow it below.</p>}
      {formError && <p role="alert" className="low-confidence">{formError}</p>}
    </form>
    {error && <p role="alert" className="low-confidence">{error}</p>}
    <div className="card" style={{ padding: 16 }}>
      <b>Your reports</b>
      <div className="table-scroll"><table><thead><tr><th>SENT</th><th>ABOUT</th><th>CLAIMED</th><th>STATUS</th><th>ANSWER</th></tr></thead><tbody>
        {claims?.length === 0 && <tr><td colSpan={5} className="muted">You have not reported anything.</td></tr>}
        {claims?.map((c) => <tr key={c.id}><td>{asDate(c.created_at)}</td><td><b>{KINDS[c.kind] ?? c.kind}</b><small>{c.order_ref ?? ''}</small></td><td>{money.format(Number(c.amount_claimed))}</td><td>{STATUS[c.status] ?? c.status}{c.amount_approved ? <small>Approved {money.format(Number(c.amount_approved))}</small> : null}</td><td><small>{c.resolution_note ?? ''}</small></td></tr>)}
      </tbody></table></div>
    </div>
  </div>;
}

/** The company's side: every claim, with the decision controls. */
export function StaffClaims({ list, update, canDecide }: { list: (status?: string) => Promise<Claim[]>; update: (id: string, input: { status?: string; amount_approved?: string; resolution_note?: string; internal_note?: string }) => Promise<Claim>; canDecide: boolean }) {
  const [filter, setFilter] = useState('');
  const { claims, error, reload } = useClaims(() => list(filter || undefined));
  const [actionError, setActionError] = useState('');
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [amounts, setAmounts] = useState<Record<string, string>>({});
  useEffect(() => { reload(); }, [filter, reload]);
  async function act(claim: Claim, input: Parameters<typeof update>[1]) {
    try { await update(claim.id, { resolution_note: notes[claim.id]?.trim() || undefined, ...input }); setActionError(''); reload(); } catch (exc) { setActionError(friendlyMessage(exc)); }
  }
  return <div className="card" style={{ padding: 16, marginBottom: 16 }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}><b>Claims and disputes</b>
      <select style={inputStyle} value={filter} onChange={(event) => setFilter(event.target.value)} aria-label="Show claims"><option value="">All</option>{Object.entries(STATUS).map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></div>
    {(error || actionError) && <p role="alert" className="low-confidence">{actionError || error}</p>}
    <div className="table-scroll"><table><thead><tr><th>SHOP</th><th>ABOUT</th><th>CLAIMED</th><th>STATUS</th><th>DECISION</th></tr></thead><tbody>
      {claims?.length === 0 && <tr><td colSpan={5} className="muted">No claims.</td></tr>}
      {claims?.map((c) => <tr key={c.id}>
        <td><b>{c.merchant_name}</b><small>{asDate(c.created_at)}</small></td>
        <td><b>{KINDS[c.kind] ?? c.kind}</b><small>{c.order_ref ?? ''}</small><small>{c.description}</small></td>
        <td>{money.format(Number(c.amount_claimed))}</td>
        <td>{STATUS[c.status] ?? c.status}{c.amount_approved ? <small>Approved {money.format(Number(c.amount_approved))}</small> : null}</td>
        <td>{canDecide && (c.status === 'open' || c.status === 'investigating')
          ? <span style={{ display: 'grid', gap: 6 }}>
            <input style={inputStyle} placeholder="Message to the shop (needed to reject)" aria-label="Message to the shop" value={notes[c.id] ?? ''} onChange={(event) => setNotes({ ...notes, [c.id]: event.target.value })} />
            <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {c.status === 'open' && <button className="button secondary" onClick={() => act(c, { status: 'investigating' })}>Look into it</button>}
              <input style={{ ...inputStyle, width: 120 }} type="number" min="0" placeholder={String(Number(c.amount_claimed))} aria-label="Approved amount" value={amounts[c.id] ?? ''} onChange={(event) => setAmounts({ ...amounts, [c.id]: event.target.value })} />
              <button className="button primary" onClick={() => act(c, { status: 'approved', amount_approved: amounts[c.id] || undefined })}>Approve</button>
              <button className="button secondary" onClick={() => act(c, { status: 'rejected' })}>Reject</button>
            </span></span>
          : canDecide && c.status === 'approved' ? <button className="button secondary" onClick={() => act(c, { status: 'paid' })}>Mark as paid</button> : <small>{c.resolution_note ?? ''}</small>}</td>
      </tr>)}
    </tbody></table></div>
  </div>;
}
