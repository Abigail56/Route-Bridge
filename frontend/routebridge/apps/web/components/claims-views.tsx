'use client';

import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { friendlyMessage, type Claim, type PortalOrder } from '../lib/api';

const money = new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN', maximumFractionDigits: 0 });
const inputStyle = { padding: '8px 10px', borderRadius: 8, border: '1px solid var(--line, #d0d5dd)', background: 'transparent', color: 'inherit', font: 'inherit' } as const;
const KINDS: Record<string, string> = { dispute: 'Dispute', refund: 'Refund', damage: 'Damaged goods', loss: 'Lost parcel' };
const STATUS: Record<string, string> = { open: 'Received', investigating: 'Being looked into', approved: 'Approved', rejected: 'Not approved', paid: 'Paid' };
const asMoment = (iso: string) => new Date(iso.endsWith('Z') || /[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
const asDate = (iso: string) => asMoment(iso).toLocaleDateString('en-NG');
const asTime = (iso: string) => asMoment(iso).toLocaleString('en-NG', { dateStyle: 'medium', timeStyle: 'short' });
const CLOSED = ['rejected', 'paid'];

function useClaims(load: () => Promise<Claim[]>) {
  const [claims, setClaims] = useState<Claim[] | null>(null);
  const [error, setError] = useState('');
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const reload = useCallback(() => load().then((rows) => { setClaims(rows); setError(''); }).catch((exc) => setError(friendlyMessage(exc))), []);
  useEffect(() => { reload(); }, [reload]);
  // new replies appear on their own, without a refresh
  useEffect(() => { const timer = window.setInterval(() => { if (!document.hidden) reload(); }, 15000); return () => window.clearInterval(timer); }, [reload]);
  return { claims, error, reload };
}

/** The conversation under one problem: what was reported, then the replies in order. `mine` is the side that is looking at it. */
function Thread({ claim, mine }: { claim: Claim; mine: 'merchant' | 'company' }) {
  const bubbles = [{ id: 'first', author: claim.raised_by === 'staff' ? 'company' : 'merchant', body: claim.description, created_at: claim.created_at }, ...(claim.messages ?? [])];
  return <div style={{ display: 'grid', gap: 6, margin: '8px 0' }} aria-label="Conversation">
    {bubbles.map((m) => {
      const own = m.author === mine;
      return <div key={m.id} style={{ justifySelf: own ? 'end' : 'start', maxWidth: '85%', padding: '8px 12px', borderRadius: 12, background: own ? 'rgba(255,122,41,.14)' : 'rgba(15,39,68,.08)' }}>
        <small className="muted" style={{ display: 'block' }}>{m.author === 'merchant' ? (mine === 'merchant' ? 'You' : claim.merchant_name ?? 'The shop') : (mine === 'company' ? 'You' : 'The company')} · {asTime(m.created_at)}</small>
        <span style={{ whiteSpace: 'pre-wrap' }}>{m.body}</span>
      </div>;
    })}
  </div>;
}

function ReplyBox({ send, placeholder, label }: { send: (body: string) => Promise<unknown>; placeholder: string; label: string }) {
  const [body, setBody] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!body.trim()) return;
    setBusy(true);
    try { await send(body.trim()); setBody(''); setError(''); } catch (exc) { setError(friendlyMessage(exc)); } finally { setBusy(false); }
  }
  return <form onSubmit={submit} style={{ display: 'grid', gap: 6 }}>
    <textarea value={body} onChange={(event) => setBody(event.target.value)} rows={2} maxLength={1000} placeholder={placeholder} aria-label={label} style={inputStyle} />
    <div><button className="button secondary" type="submit" disabled={busy || !body.trim()}>{busy ? 'Sending…' : 'Send message'}</button></div>
    {error && <p role="alert" className="low-confidence" style={{ margin: 0 }}>{error}</p>}
  </form>;
}

/** The shop's side: report a problem about one of its orders, and follow the company's replies. */
export function PortalClaims({ list, open, reply, orders }: { list: () => Promise<Claim[]>; open: (input: { kind: string; description: string; amount_claimed: string; order_id: string }) => Promise<Claim>; reply: (id: string, body: string) => Promise<Claim>; orders: PortalOrder[] }) {
  const { claims, error, reload } = useClaims(list);
  const [formError, setFormError] = useState('');
  const [sent, setSent] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    try {
      await open({ kind: String(data.get('kind')), description: String(data.get('description')).trim(), amount_claimed: String(data.get('amount') || '0'), order_id: String(data.get('order')) });
      form.reset(); setFormError(''); setSent(true); reload();
    } catch (exc) { setFormError(friendlyMessage(exc)); setSent(false); }
  }
  return <div style={{ display: 'grid', gap: 16 }}>
    <form className="card" style={{ padding: 16, display: 'grid', gap: 10 }} onSubmit={submit}>
      <b>Report a problem</b>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <select name="kind" style={inputStyle} aria-label="What happened" defaultValue="damage">{Object.entries(KINDS).map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select>
        <select name="order" required style={inputStyle} aria-label="Which order" defaultValue=""><option value="" disabled>Choose the order</option>{orders.slice(0, 100).map((o) => <option key={o.id} value={o.id}>{o.external_ref} · {o.customer_name ?? ''}</option>)}</select>
        <input name="amount" type="number" min="0" step="1" placeholder="Amount you are claiming (₦)" style={inputStyle} aria-label="Amount claimed" />
      </div>
      <textarea name="description" required minLength={5} maxLength={2000} rows={3} placeholder="Tell us what happened" style={inputStyle} aria-label="What happened, in your words" />
      <div><button className="button primary" type="submit">Send to the company</button></div>
      {sent && <p role="status">Sent to the company. Their reply will appear here.</p>}
      {formError && <p role="alert" className="low-confidence">{formError}</p>}
    </form>
    {error && <p role="alert" className="low-confidence">{error}</p>}
    <div className="card" style={{ padding: 16, display: 'grid', gap: 12 }}>
      <b>Your reports</b>
      {claims?.length === 0 && <p className="muted" style={{ margin: 0 }}>You have not reported anything.</p>}
      {claims?.map((c) => {
        const answered = (c.messages ?? []).some((m) => m.author === 'company');
        return <div key={c.id} className="drawer-block" style={{ display: 'grid', gap: 4 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
            <span><b>{KINDS[c.kind] ?? c.kind}</b>{c.order_ref ? <> · order {c.order_ref}</> : null} · {asDate(c.created_at)}</span>
            <span><b>{STATUS[c.status] ?? c.status}</b>{c.amount_approved ? <small> · approved {money.format(Number(c.amount_approved))}</small> : null}{Number(c.amount_claimed) ? <small className="muted"> · claimed {money.format(Number(c.amount_claimed))}</small> : null}</span>
          </div>
          <Thread claim={c} mine="merchant" />
          {!answered && !CLOSED.includes(c.status) && <small className="muted">Waiting for the company to reply.</small>}
          {CLOSED.includes(c.status) ? <small className="muted">This report is closed.</small> : <ReplyBox send={async (body) => { await reply(c.id, body); reload(); }} placeholder="Add a message for the company" label={`Message about ${KINDS[c.kind] ?? 'this problem'}`} />}
        </div>;
      })}
    </div>
  </div>;
}

/** The company's side: every problem a shop sent, the conversation, and the decision controls. */
export function StaffClaims({ list, update, reply, canDecide }: { list: (status?: string) => Promise<Claim[]>; update: (id: string, input: { status?: string; amount_approved?: string; resolution_note?: string; internal_note?: string }) => Promise<Claim>; reply: (id: string, body: string) => Promise<Claim>; canDecide: boolean }) {
  const [filter, setFilter] = useState('');
  const { claims, error, reload } = useClaims(() => list(filter || undefined));
  const [actionError, setActionError] = useState('');
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [amounts, setAmounts] = useState<Record<string, string>>({});
  useEffect(() => { reload(); }, [filter, reload]);
  async function act(claim: Claim, input: Parameters<typeof update>[1]) {
    try { await update(claim.id, { resolution_note: notes[claim.id]?.trim() || undefined, ...input }); setNotes({ ...notes, [claim.id]: '' }); setActionError(''); reload(); } catch (exc) { setActionError(friendlyMessage(exc)); }
  }
  const waiting = (claims ?? []).filter((c) => c.awaiting_company).length;
  return <div className="card" style={{ padding: 16, marginBottom: 16, display: 'grid', gap: 12 }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}><b>Problems from your shops{waiting ? ` · ${waiting} waiting for your reply` : ''}</b>
      <select style={inputStyle} value={filter} onChange={(event) => setFilter(event.target.value)} aria-label="Show problems"><option value="">All</option>{Object.entries(STATUS).map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></div>
    {(error || actionError) && <p role="alert" className="low-confidence" style={{ margin: 0 }}>{actionError || error}</p>}
    {claims?.length === 0 && <p className="muted" style={{ margin: 0 }}>No problems reported.</p>}
    {claims?.map((c) => <div key={c.id} className="drawer-block" style={{ display: 'grid', gap: 4, borderLeft: c.awaiting_company ? '4px solid #ff7a29' : undefined }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <span><b>{c.merchant_name}</b> · {KINDS[c.kind] ?? c.kind}{c.order_ref ? <> · order {c.order_ref}</> : null} · {asDate(c.created_at)}</span>
        <span><b>{STATUS[c.status] ?? c.status}</b>{Number(c.amount_claimed) ? <small> · claimed {money.format(Number(c.amount_claimed))}</small> : null}{c.amount_approved ? <small> · approved {money.format(Number(c.amount_approved))}</small> : null}{c.awaiting_company ? <small style={{ color: '#c2410c' }}> · needs your reply</small> : null}</span>
      </div>
      <Thread claim={c} mine="company" />
      {canDecide && !CLOSED.includes(c.status) && <ReplyBox send={async (body) => { await reply(c.id, body); reload(); }} placeholder="Reply to the shop" label={`Reply to ${c.merchant_name ?? 'the shop'}`} />}
      {canDecide && (c.status === 'open' || c.status === 'investigating') && <span style={{ display: 'grid', gap: 6 }}>
        <input style={inputStyle} placeholder="Message sent with your decision (needed to reject)" aria-label="Message with the decision" value={notes[c.id] ?? ''} onChange={(event) => setNotes({ ...notes, [c.id]: event.target.value })} />
        <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {c.status === 'open' && <button className="button secondary" onClick={() => act(c, { status: 'investigating' })}>Look into it</button>}
          <input style={{ ...inputStyle, width: 120 }} type="number" min="0" placeholder={String(Number(c.amount_claimed))} aria-label="Approved amount" value={amounts[c.id] ?? ''} onChange={(event) => setAmounts({ ...amounts, [c.id]: event.target.value })} />
          <button className="button primary" onClick={() => act(c, { status: 'approved', amount_approved: amounts[c.id] || undefined })}>Approve</button>
          <button className="button secondary" onClick={() => act(c, { status: 'rejected' })}>Reject</button>
        </span></span>}
      {canDecide && c.status === 'approved' && <div><button className="button secondary" onClick={() => act(c, { status: 'paid' })}>Mark as paid</button></div>}
    </div>)}
  </div>;
}
