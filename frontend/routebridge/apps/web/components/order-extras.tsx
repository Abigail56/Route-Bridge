'use client';

import { useCallback, useEffect, useState } from 'react';
import { friendlyMessage, type DeliveryEvidence, type TrackingShare } from '../lib/api';

const when = (iso: string) => new Date(/(Z|[+-]\d\d:\d\d)$/.test(iso) ? iso : `${iso}Z`).toLocaleString('en-NG', { dateStyle: 'medium', timeStyle: 'short' });
const money = new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN', maximumFractionDigits: 0 });

/** The space where an order's tracking link goes to the customer: who it is for, the text, and buttons to send it. */
export function TrackingSpace({ load, send, refreshKey = 0 }: { load: () => Promise<TrackingShare>; send: (channel: 'sms' | 'whatsapp') => Promise<TrackingShare>; refreshKey?: number }) {
  const [share, setShare] = useState<TrackingShare | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [copied, setCopied] = useState('');
  const reload = useCallback(() => load().then((row) => { setShare(row); setError(''); }).catch((exc) => setError(friendlyMessage(exc))), [load]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { reload(); }, [reload, refreshKey]);

  async function queue(channel: 'sms' | 'whatsapp') {
    setBusy(channel); setError('');
    try { setShare(await send(channel)); } catch (exc) { setError(friendlyMessage(exc)); } finally { setBusy(''); }
  }
  async function copy(what: 'link' | 'message', text: string) {
    try { await navigator.clipboard.writeText(text); setCopied(what); setTimeout(() => setCopied(''), 1500); } catch { /* clipboard unavailable */ }
  }
  const digits = (share?.phone ?? '').replace(/\D/g, '');
  const whatsapp = share?.link && digits ? `https://wa.me/${digits}?text=${encodeURIComponent(share.message)}` : '';
  return <div className="drawer-block"><span className="eyebrow">SEND THE TRACKING LINK TO YOUR CUSTOMER</span>
    {!share && !error && <small className="muted">Loading…</small>}
    {share && <>
      <b>{share.customer_name ?? 'Customer'}{share.phone ? ` · ${share.phone}` : ''}</b>
      {share.link ? <>
        <small style={{ wordBreak: 'break-all' }}>{share.link}</small>
        <small className="muted" style={{ whiteSpace: 'normal' }}>Message: “{share.message}”</small>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
          {whatsapp && <a className="button primary" href={whatsapp} target="_blank" rel="noopener noreferrer">Send on WhatsApp now</a>}
          <button className="button secondary" type="button" disabled={!!busy} onClick={() => queue('sms')}>{busy === 'sms' ? 'Sending…' : 'Send by SMS'}</button>
          <button className="button secondary" type="button" disabled={!!busy} onClick={() => queue('whatsapp')}>{busy === 'whatsapp' ? 'Sending…' : 'Send by WhatsApp message'}</button>
          <button className="button secondary" type="button" onClick={() => copy('message', share.message)}>{copied === 'message' ? 'Message copied' : 'Copy message'}</button>
          <button className="button secondary" type="button" onClick={() => copy('link', share.link!)}>{copied === 'link' ? 'Link copied' : 'Copy link'}</button>
        </div>
        {!share.sms_connected && <small className="muted" style={{ whiteSpace: 'normal', marginTop: 6 }}>Text messages are not connected to a sender yet, so “Send by SMS” and “Send by WhatsApp message” are only recorded here. To reach the customer right now, use <b>Send on WhatsApp now</b> or copy the message.</small>}
      </> : <small className="muted">This order has no active tracking link yet.</small>}
      {share.sent.length > 0 && <div style={{ marginTop: 8, display: 'grid', gap: 2 }}>
        <span className="eyebrow">ALREADY SENT</span>
        {share.sent.map((row, index) => <small key={`${row.at}-${index}`}>{row.channel === 'sms' ? 'SMS' : 'WhatsApp'} · {row.status === 'sent' ? 'delivered to the sender' : row.status} · {when(row.at)}</small>)}
      </div>}
    </>}
    {error && <p role="alert" className="low-confidence" style={{ margin: '6px 0 0' }}>{error}</p>}
  </div>;
}

/** Evidence of delivery: who received it, when, the customer's code, the photo taken at the door, and the cash. */
export function EvidenceCard({ load, refreshKey = 0 }: { load: () => Promise<DeliveryEvidence>; refreshKey?: number }) {
  const [data, setData] = useState<DeliveryEvidence | null>(null);
  const [error, setError] = useState('');
  const [zoom, setZoom] = useState('');
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load().then((row) => { setData(row); setError(''); }).catch((exc) => setError(friendlyMessage(exc))); }, [load, refreshKey]);
  return <div className="drawer-block"><span className="eyebrow">EVIDENCE OF DELIVERY</span>
    {!data && !error && <small className="muted">Loading…</small>}
    {data && !data.available && <small className="muted" style={{ whiteSpace: 'normal' }}>No evidence yet. The photo, the person who received the parcel and the customer&apos;s code appear here once the rider completes the delivery.</small>}
    {data?.available && <>
      <b>{data.code_verified ? <span className="rb-verified">✓ Customer&apos;s code verified</span> : <span className="low-confidence">Completed without the customer&apos;s code</span>}</b>
      <small>Delivered {data.delivered_at ? when(data.delivered_at) : ''}{data.recipient_name ? ` · received by ${data.recipient_name}` : ''}</small>
      {data.rider_name && <small>Rider: {data.rider_name}</small>}
      {data.cash_collected !== null && data.cash_collected !== undefined && <small>Cash collected {money.format(Number(data.cash_collected))} of {money.format(Number(data.cash_expected))} expected</small>}
      {data.photo
        // eslint-disable-next-line @next/next/no-img-element
        ? <button type="button" onClick={() => setZoom(data.photo!)} aria-label="Open the delivery photo" style={{ border: 0, padding: 0, background: 'none', cursor: 'zoom-in', marginTop: 8 }}><img src={data.photo} alt="Photo taken by the rider at delivery" style={{ width: '100%', maxHeight: 260, objectFit: 'cover', borderRadius: 12 }} /></button>
        : <small className="muted" style={{ whiteSpace: 'normal', marginTop: 6 }}>{data.has_photo ? 'The photo could not be loaded right now. Try again in a moment.' : 'No photo was taken for this delivery.'}</small>}
      {data.signature && <><span className="eyebrow" style={{ marginTop: 8 }}>SIGNATURE</span>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={data.signature} alt="Customer signature" style={{ width: '100%', maxHeight: 140, objectFit: 'contain', background: '#fff', borderRadius: 12 }} /></>}
    </>}
    {error && <p role="alert" className="low-confidence" style={{ margin: '6px 0 0' }}>{error}</p>}
    {zoom && <div role="dialog" aria-label="Delivery photo" onClick={() => setZoom('')} style={{ position: 'fixed', inset: 0, zIndex: 200, background: 'rgba(6,12,28,.88)', display: 'grid', placeItems: 'center', padding: 16, cursor: 'zoom-out' }}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={zoom} alt="Delivery photo, full size" style={{ maxWidth: '100%', maxHeight: '100%', borderRadius: 12 }} />
    </div>}
  </div>;
}
