'use client';

import { useCallback, useEffect, useState } from 'react';
import { friendlyMessage, type ApiClient, type Driver } from '../lib/api';
import { buildDriverLink, isLocalOnlyOrigin, validHours, whatsappLink } from '../lib/driver-access';

/** Gives one driver their access: a link and a QR code that open the driver app already signed in, valid for one shift. */
export function DriverAccessDialog({ api, tenantId, driver, close }: { api: ApiClient; tenantId: string; driver: Driver; close: () => void }) {
  const [link, setLink] = useState('');
  const [qr, setQr] = useState('');
  const [hours, setHours] = useState(12);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const localOnly = typeof window !== 'undefined' && isLocalOnlyOrigin(window.location.origin);

  const issue = useCallback(async () => {
    setBusy(true); setError(''); setCopied(false);
    try {
      const result = await api.issueDriverToken(tenantId, driver.id);
      const url = buildDriverLink(window.location.origin, result.access_token);
      const QRCode = (await import('qrcode')).default;
      setQr(await QRCode.toDataURL(url, { width: 360, margin: 2, errorCorrectionLevel: 'M', color: { dark: '#0b1f4b', light: '#ffffff' } }));
      setLink(url);
      setHours(validHours(result.expires_in));
    } catch (exc) { setError(friendlyMessage(exc)); } finally { setBusy(false); }
  }, [api, tenantId, driver.id]);

  useEffect(() => { issue(); }, [issue]);

  async function copy() {
    try { await navigator.clipboard.writeText(link); setCopied(true); } catch { setCopied(false); }
  }

  return <div className="drawer-backdrop" onClick={close}><aside className="drawer" onClick={(event) => event.stopPropagation()} aria-label={`Access link for ${driver.name}`}>
    <button className="close" onClick={close} aria-label="Close">×</button>
    <span className="eyebrow">DRIVER ACCESS</span>
    <h2>{driver.name}</h2>
    <p className="muted">Give {driver.name.split(' ')[0]} this link or QR code. It opens the driver app already signed in, and works for {hours} hours (one shift).</p>
    {error && <p role="alert" className="low-confidence">{error}</p>}
    {busy && !link && <div className="skeleton" style={{ height: 280, borderRadius: 16 }} />}
    {link && <>
      <div className="qr-box">{/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={qr} alt={`QR code that signs ${driver.name} in to the driver app`} width={280} height={280} /></div>
      <p className="muted" style={{ textAlign: 'center', marginTop: 8 }}>The driver scans this with their phone camera.</p>
      {localOnly && <p className="tracking-hint" role="note">This link will not open on a phone. It uses the address &quot;localhost&quot;, which means &quot;this computer&quot;. Open RouteBridge using your computer&apos;s network address, or your real website address, and make the link again.</p>}
      <div className="drawer-block">
        <span className="eyebrow">OR SEND THE LINK</span>
        <div className="link-row">
          <button className="button primary" onClick={copy}>{copied ? 'Link copied' : 'Copy link'}</button>
          <a className="button secondary" href={whatsappLink(driver.phone, link, driver.name, hours)} target="_blank" rel="noreferrer">Send on WhatsApp</a>
        </div>
        <small className="muted">WhatsApp opens a message to {driver.phone}.</small>
      </div>
      <div className="drawer-block">
        <span className="eyebrow">TELL THE DRIVER</span>
        <ol className="steps">
          <li>Open the link (or scan the code) on your phone.</li>
          <li>When asked, tap <b>Allow</b> for location, so dispatch and customers can see you on the way.</li>
          <li>Tap <b>Add to Home screen</b> (or <b>Install app</b>) so it opens like a normal app. It keeps working without signal.</li>
        </ol>
        <small className="muted">Anyone holding this link can act as {driver.name.split(' ')[0]} until it expires. Share it only with them. Making a new link does not cancel an older one.</small>
      </div>
    </>}
    <div className="drawer-actions"><button className="button secondary" onClick={issue} disabled={busy}>{busy ? 'Making…' : 'Make a new link'}</button><button className="button secondary" onClick={close}>Close</button></div>
  </aside></div>;
}
