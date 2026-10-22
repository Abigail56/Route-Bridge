'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { friendlyMessage, type ApiClient, type Profile } from '../lib/api';
import { RoleAndId } from './signup-role';
import { EMPTY_PLACE, PlaceFields, type Place } from './place-fields';

const box = { maxWidth: 520, margin: '10vh auto', padding: 28, border: '1px solid var(--line, #d9e2e0)', borderRadius: 14, background: 'var(--white, #fff)' } as const;
const input = { width: '100%', padding: '12px 14px', borderRadius: 8, border: '1px solid var(--line, #cfd9d7)', background: 'transparent', color: 'inherit', font: 'inherit', marginBottom: 12, boxSizing: 'border-box' } as const;

/** Shown when a signed-in user belongs to no workspace yet. */
export function FirstRunScreen({ api, profile, onCreated, accountMenu, onOpenPlatform }: { api: ApiClient; profile: Profile; onCreated: () => void; accountMenu?: React.ReactNode; onOpenPlatform?: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState('');
  async function copy(text: string, message: string) {
    try { await navigator.clipboard.writeText(text); setCopied(message); } catch { setCopied('Copying is blocked in this browser. Select the id above and copy it by hand.'); }
  }

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = String(new FormData(event.currentTarget).get('name') ?? '').trim();
    if (name.length < 2) { setError('Enter your company or team name.'); return; }
    setBusy(true);
    setError('');
    try { await api.createTenant(name); onCreated(); } catch (exc) { setError(friendlyMessage(exc)); setBusy(false); }
  }

  return <main style={box}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <b style={{ fontSize: 13, letterSpacing: 1 }}>ROUTEBRIDGE</b>{accountMenu}
    </div>
    <h1 style={{ fontSize: 28, margin: '18px 0 6px' }}>Welcome{profile.name ? `, ${profile.name}` : ''}</h1>
    {profile.is_platform_admin ? <>
      <p style={{ color: 'var(--muted, #6b7a79)', lineHeight: 1.5 }}>You are not part of a workspace yet. Create one for your company. You will be its owner, and can then add merchants, delivery zones, drivers and teammates.</p>
      <form onSubmit={create}>
        <input name="name" defaultValue="RouteBridge" placeholder="Company or team name" style={input} maxLength={200} aria-label="Workspace name" autoFocus />
        <button type="submit" className="button primary" disabled={busy} style={{ width: '100%', padding: 14 }}>{busy ? 'Creating…' : 'Create workspace'}</button>
      </form>
      {onOpenPlatform && <button className="button secondary" style={{ width: '100%', padding: 14, marginTop: 10 }} onClick={onOpenPlatform}>Open platform console instead</button>}
    </> : profile.details_complete === false ? <DetailsStep api={api} profile={profile} onSaved={onCreated} /> : <>
      <p style={{ color: 'var(--muted, #6b7a79)', lineHeight: 1.5 }}>You are signed in, but your account is not linked to a workspace yet. Choose what you will do, then press <b>Send to the Admin</b>: your ID goes straight to their dashboard and they are alerted. Once they add you, you can continue.</p>
      <RoleAndId subject={profile.subject ?? ''} email={profile.email} copy={copy} api={api} />
      {copied && <p role="status" style={{ marginTop: 10, color: 'var(--teal-dark, #087f56)', fontWeight: 600 }}>{copied}</p>}
      <p style={{ color: 'var(--muted, #6b7a79)', lineHeight: 1.5, marginTop: 18 }}>Once they have added you, press the button below.</p>
      <button className="button secondary" onClick={onCreated}>I have been added — check again</button>
    </>}
    {error && <p role="alert" className="low-confidence" style={{ marginTop: 12 }}>{error}</p>}
  </main>;
}

/** After a Google sign-up: Google gives only a name and email, so the rest of the sign-up details are asked once here. */
function DetailsStep({ api, profile, onSaved }: { api: ApiClient; profile: Profile; onSaved: () => void }) {
  const [name, setName] = useState(profile.name ?? '');
  const [place, setPlace] = useState<Place>({ ...EMPTY_PLACE, phone: profile.phone ?? '', country: profile.country || 'NG', state: profile.state ?? '', region: profile.region ?? '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError('');
    try { await api.saveMyDetails({ full_name: name.trim(), phone: place.phone.trim(), country: place.country, state: place.state.trim(), region: place.region.trim() }); onSaved(); } catch (exc) { setError(friendlyMessage(exc)); setBusy(false); }
  }
  return <form onSubmit={save} className="auth-form details-step">
    <p style={{ color: 'var(--muted, #6b7a79)', lineHeight: 1.5, margin: '0 0 10px' }}>Welcome to RouteBridge. Tell us a little more about you to finish signing up.</p>
    <label>Full name<input value={name} onChange={(event) => setName(event.target.value)} required minLength={2} maxLength={200} autoComplete="name" style={input} /></label>
    <PlaceFields value={place} onChange={setPlace} inputStyle={input} />
    {error && <p role="alert" className="low-confidence">{error}</p>}
    <button type="submit" className="button primary" disabled={busy} style={{ width: '100%', padding: 14 }}>{busy ? 'Saving…' : 'Continue'}</button>
  </form>;
}

/** "Getting started" card on the overview until merchants, zones and drivers exist. */
export function SetupChecklist({ api, tenantId, refreshKey, onGo }: { api: ApiClient; tenantId: string; refreshKey: number; onGo: (section: string, tab?: 'merchants' | 'zones' | 'members') => void }) {
  const [counts, setCounts] = useState<{ merchants: number; zones: number; drivers: number } | null>(null);
  useEffect(() => {
    let active = true;
    Promise.all([api.getMerchants(tenantId).catch(() => null), api.getZones(tenantId).catch(() => null), api.getDrivers(tenantId).catch(() => null)])
      .then(([m, z, d]) => { if (active && m && z && d) setCounts({ merchants: m.length, zones: z.length, drivers: d.length }); });
    return () => { active = false; };
  }, [api, tenantId, refreshKey]);

  if (!counts || (counts.merchants && counts.zones && counts.drivers)) return null;
  const step = (done: boolean, text: string, action: () => void, cta: string) => <li style={{ display: 'flex', justifyContent: 'space-between', gap: 12, padding: '8px 0', alignItems: 'center' }}>
    <span>{done ? '✓' : '○'} <span style={{ textDecoration: done ? 'line-through' : 'none', opacity: done ? 0.6 : 1 }}>{text}</span></span>
    {!done && <button className="button secondary" onClick={action}>{cta}</button>}
  </li>;
  return <div className="card" style={{ padding: 16, marginBottom: 24 }}>
    <b>Getting started</b>
    <ul style={{ listStyle: 'none', padding: 0, margin: '8px 0 0' }}>
      {step(counts.merchants > 0, 'Add a merchant (the business you deliver for)', () => onGo('Merchants'), 'Add merchant')}
      {step(counts.zones > 0, 'A shop adds its delivery zone when it registers', () => onGo('Merchants'), 'See shops')}
      {step(counts.drivers > 0, 'Add your first driver', () => onGo('Drivers'), 'Add driver')}
    </ul>
  </div>;
}
