'use client';

import { useState, type FormEvent } from 'react';
import { friendlyMessage, type Statement } from '../lib/api';

const money = new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN', maximumFractionDigits: 0 });
const inputStyle = { padding: '8px 10px', borderRadius: 8, border: '1px solid var(--line, #d0d5dd)', background: 'transparent', color: 'inherit', font: 'inherit' } as const;
const day = (date: Date) => date.toISOString().slice(0, 10);
const asDate = (iso: string) => new Date(iso.endsWith('Z') || /[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);

/** A payout statement for one shop over a date range, with a CSV download. Used by finance staff and, fenced to one shop, in the merchant portal. */
export function StatementCard({ load, download, title = 'Payout statement' }: { load: (from: string, to: string) => Promise<Statement>; download: (from: string, to: string) => Promise<Blob>; title?: string }) {
  const [range, setRange] = useState({ from: day(new Date(Date.now() - 30 * 86400000)), to: day(new Date()) });
  const [data, setData] = useState<Statement | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const bounds = () => [`${range.from}T00:00:00Z`, `${range.to}T23:59:59Z`] as const;

  async function show(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError('');
    try { setData(await load(...bounds())); } catch (exc) { setError(friendlyMessage(exc)); setData(null); } finally { setBusy(false); }
  }
  async function save() {
    try {
      const url = URL.createObjectURL(await download(...bounds()));
      const link = document.createElement('a');
      link.href = url; link.download = `statement-${range.from}-${range.to}.csv`; link.click();
      URL.revokeObjectURL(url);
    } catch (exc) { setError(friendlyMessage(exc)); }
  }
  const net = data ? Number(data.net_payable) : 0;
  return <div className="card" style={{ padding: 16 }}>
    <b>{title}</b>
    <form onSubmit={show} style={{ display: 'flex', gap: 8, alignItems: 'end', flexWrap: 'wrap', margin: '12px 0' }}>
      <label style={{ display: 'grid', gap: 4 }}><span className="eyebrow">FROM</span><input type="date" style={inputStyle} value={range.from} max={range.to} onChange={(event) => setRange({ ...range, from: event.target.value })} /></label>
      <label style={{ display: 'grid', gap: 4 }}><span className="eyebrow">TO</span><input type="date" style={inputStyle} value={range.to} min={range.from} onChange={(event) => setRange({ ...range, to: event.target.value })} /></label>
      <button className="button primary" type="submit" disabled={busy}>{busy ? 'Working…' : 'Show statement'}</button>
      {data && <button className="button secondary" type="button" onClick={save}>Download CSV</button>}
    </form>
    {error && <p role="alert" className="low-confidence">{error}</p>}
    {data && <>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginBottom: 12 }}>
        <div className="drawer-block"><span className="eyebrow">DELIVERIES</span><b>{data.deliveries}</b></div>
        <div className="drawer-block"><span className="eyebrow">CASH COLLECTED</span><b>{money.format(Number(data.cash_collected))}</b></div>
        <div className="drawer-block"><span className="eyebrow">DELIVERY FEES</span><b>{money.format(Number(data.delivery_fees))}</b></div>
        <div className="drawer-block"><span className="eyebrow">{net >= 0 ? 'TO PAY THE SHOP' : 'SHOP OWES'}</span><b>{money.format(Math.abs(net))}</b></div>
      </div>
      <div className="table-scroll"><table><thead><tr><th>ORDER</th><th>DELIVERED</th><th>CASH DUE</th><th>COLLECTED</th><th>FEE</th><th>NOTE</th></tr></thead><tbody>
        {data.lines.length === 0 && <tr><td colSpan={6} className="muted">No deliveries in this period.</td></tr>}
        {data.lines.map((line) => <tr key={line.order_ref + line.delivered_at}><td><b>{line.order_ref}</b></td><td>{asDate(line.delivered_at).toLocaleDateString('en-NG')}</td><td>{money.format(Number(line.cod_due))}</td><td>{money.format(Number(line.cash_collected))}</td><td>{money.format(Number(line.delivery_fee))}</td><td>{line.note ? <small className="low-confidence">{line.note}</small> : ''}</td></tr>)}
      </tbody></table></div>
    </>}
  </div>;
}
