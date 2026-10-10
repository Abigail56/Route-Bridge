'use client';

import { usePathname } from 'next/navigation';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ROLE_CHOICES, buildMessage, idLabel, loadChoice, roleInfo, saveChoice, type Choice, type RoleKey } from '../lib/signup-role';

const field = { padding: '12px 14px', borderRadius: 12, border: '1.5px solid var(--line, #d9e2e0)', background: 'transparent', color: 'inherit', font: 'inherit', width: '100%', boxSizing: 'border-box', minHeight: 46 } as const;

/**
 * Sits in front of the sign-up page. Asks what the person will do on RouteBridge, so that once they are signed in the id they send
 * to the owner says what they are asking to be added as. Skipping is fine: they can choose on the next screen too.
 */
export function SignUpRoleStep({ children }: { children: ReactNode }) {
  const pathname = (usePathname() ?? '').replace(/\/+$/, '');
  const [open, setOpen] = useState(false);
  const [role, setRole] = useState<RoleKey | null>(null);
  const [shop, setShop] = useState('');
  const first = useRef<HTMLButtonElement | null>(null);
  // only on the first page of sign-up, and only when nothing was chosen yet (Clerk's later pages live under /sign-up/…)
  useEffect(() => { if (pathname === '/sign-up' && !loadChoice()) setOpen(true); }, [pathname]);
  useEffect(() => { if (open) first.current?.focus(); }, [open]);
  function done(save: boolean) {
    if (save && role) saveChoice({ role, ...(role === 'merchant_user' && shop.trim() ? { shop: shop.trim() } : {}) });
    setOpen(false);
  }
  return <>
    {children}
    {open && <div role="dialog" aria-modal="true" aria-labelledby="role-step-title" style={{ position: 'fixed', inset: 0, zIndex: 60, background: 'rgba(15,39,68,.78)', overflowY: 'auto', display: 'flex', justifyContent: 'center', alignItems: 'flex-start', padding: '16px 16px 32px', boxSizing: 'border-box' }}>
      <div style={{ background: 'var(--white, #fff)', color: 'var(--ink, #14233b)', borderRadius: 16, padding: 'clamp(18px, 4vw, 28px)', width: '100%', maxWidth: 480, marginTop: 'clamp(8px, 6vh, 56px)', boxShadow: '0 20px 60px rgba(0,0,0,.35)' }}>
        <h2 id="role-step-title" style={{ margin: '0 0 6px', fontSize: 'clamp(21px, 5vw, 26px)' }}>What will you do on RouteBridge?</h2>
        <p style={{ margin: '0 0 16px', lineHeight: 1.5, color: 'var(--muted, #5b6b78)' }}>Pick one. After you sign up you will get an ID to send to the person who runs the company. They use it to add you in the right place.</p>
        <div role="radiogroup" aria-label="Your role" style={{ display: 'grid', gap: 10 }}>
          {ROLE_CHOICES.map((choice, index) => <button key={choice.role} ref={index === 0 ? first : undefined} type="button" role="radio" aria-checked={role === choice.role} onClick={() => setRole(choice.role)}
            style={{ textAlign: 'left', padding: '12px 14px', minHeight: 56, borderRadius: 12, cursor: 'pointer', font: 'inherit', color: 'inherit', background: role === choice.role ? 'rgba(255,122,41,.12)' : 'transparent', border: `2px solid ${role === choice.role ? '#ff7a29' : 'var(--line, #d9e2e0)'}` }}>
            <b style={{ display: 'block' }}>{choice.label}</b><small style={{ color: 'var(--muted, #5b6b78)' }}>{choice.hint}</small>
          </button>)}
        </div>
        {role === 'merchant_user' && <label style={{ display: 'grid', gap: 6, marginTop: 14 }}><span className="eyebrow">Your shop&apos;s name (optional)</span>
          <input value={shop} onChange={(event) => setShop(event.target.value)} maxLength={120} placeholder="Ada Foods" style={field} autoComplete="organization" /></label>}
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 18 }}>
          <button type="button" className="button primary" style={{ flex: '1 1 180px', minHeight: 46 }} disabled={!role} onClick={() => done(true)}>Continue to sign up</button>
          <button type="button" className="button secondary" style={{ flex: '1 1 140px', minHeight: 46 }} onClick={() => done(false)}>Choose later</button>
        </div>
      </div>
    </div>}
  </>;
}

/** The ID card on the "not linked yet" screen: the id the owner needs, what it is for, and a message ready to send. */
export function RoleAndId({ subject, email, copy }: { subject: string; email: string | null; copy: (text: string, message: string) => void }) {
  const [choice, setChoice] = useState<Choice | null>(null);
  useEffect(() => { setChoice(loadChoice()); }, []);
  function change(next: Choice | null) { setChoice(next); saveChoice(next); }
  const role = choice?.role ?? null;
  const info = role ? roleInfo(role) : null;
  const label = idLabel(role);
  return <div>
    <label style={{ display: 'grid', gap: 6, marginBottom: 14 }}><span className="eyebrow">I AM JOINING AS</span>
      <select value={role ?? ''} onChange={(event) => change(event.target.value ? { role: event.target.value as RoleKey, ...(choice?.shop ? { shop: choice.shop } : {}) } : null)} style={field} aria-label="I am joining as">
        <option value="">Choose what you will do…</option>
        {ROLE_CHOICES.map((item) => <option key={item.role} value={item.role}>{item.label}</option>)}
      </select></label>
    {role === 'merchant_user' && <label style={{ display: 'grid', gap: 6, marginBottom: 14 }}><span className="eyebrow">YOUR SHOP&apos;S NAME (OPTIONAL)</span>
      <input value={choice?.shop ?? ''} onChange={(event) => change({ role: 'merchant_user', shop: event.target.value })} maxLength={120} placeholder="Ada Foods" style={field} autoComplete="organization" aria-label="Your shop's name" /></label>}
    <span className="eyebrow">{label.toUpperCase()}</span>
    <code style={{ display: 'block', padding: 12, borderRadius: 8, background: 'rgba(127,127,127,.12)', wordBreak: 'break-all', marginTop: 6 }} data-testid="my-user-id">{subject}</code>
    <p className="muted" style={{ margin: '8px 0 0', lineHeight: 1.5 }}>{info
      ? <>Send this to the owner. They open <b>{info.where}</b> and add you with it. {role === 'merchant_user' ? 'Once added, your shop also gets its own Shop ID, shown on your dashboard.' : ''}</>
      : 'Choose what you will do above, then send this ID to the owner.'}</p>
    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 14 }}>
      <button className="button primary" style={{ minHeight: 46 }} onClick={() => copy(subject, `Your ${label} is copied.`)}>Copy my ID</button>
      <button className="button secondary" style={{ minHeight: 46 }} onClick={() => copy(buildMessage({ subject, email, choice }), 'Message copied. Paste it into WhatsApp or SMS.')}>Copy a message to send</button>
    </div>
  </div>;
}
