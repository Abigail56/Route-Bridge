'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { friendlyMessage, type ApiClient, type Profile } from '../lib/api';

const box = { maxWidth: 520, margin: '10vh auto', padding: 28, border: '1px solid var(--line, #d9e2e0)', borderRadius: 14, background: 'var(--white, #fff)' } as const;
const input = { width: '100%', padding: '12px 14px', borderRadius: 8, border: '1px solid var(--line, #cfd9d7)', background: 'transparent', color: 'inherit', font: 'inherit', marginBottom: 12, boxSizing: 'border-box' } as const;

/** Shown when a signed-in user belongs to no workspace yet. */
export function FirstRunScreen({ api, profile, onCreated, accountMenu, onOpenPlatform }: { api: ApiClient; profile: Profile; onCreated: () => void; accountMenu?: React.ReactNode; onOpenPlatform?: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

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
        <input name="name" placeholder="Company or team name" style={input} maxLength={200} aria-label="Workspace name" autoFocus />
        <button type="submit" className="button primary" disabled={busy} style={{ width: '100%', padding: 14 }}>{busy ? 'Creating…' : 'Create workspace'}</button>
      </form>
      {onOpenPlatform && <button className="button secondary" style={{ width: '100%', padding: 14, marginTop: 10 }} onClick={onOpenPlatform}>Open platform console instead</button>}
    </> : <>
      <p style={{ color: 'var(--muted, #6b7a79)', lineHeight: 1.5 }}>Your account is not linked to a workspace yet. Ask your administrator to add you, and send them this id so they can find you:</p>
      <code style={{ display: 'block', padding: 12, borderRadius: 8, background: 'rgba(127,127,127,.12)', wordBreak: 'break-all' }}>{profile.subject}</code>
      <button className="button secondary" style={{ marginTop: 14 }} onClick={onCreated}>I have been added — check again</button>
    </>}
    {error && <p role="alert" className="low-confidence" style={{ marginTop: 12 }}>{error}</p>}
  </main>;
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
      {step(counts.merchants > 0, 'Add a merchant (the business you deliver for)', () => onGo('Settings', 'merchants'), 'Add merchant')}
      {step(counts.zones > 0, 'Create a delivery zone', () => onGo('Settings', 'zones'), 'Add zone')}
      {step(counts.drivers > 0, 'Add your first driver', () => onGo('Drivers'), 'Add driver')}
    </ul>
  </div>;
}
