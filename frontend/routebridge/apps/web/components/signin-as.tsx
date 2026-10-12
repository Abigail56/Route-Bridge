'use client';

import { useEffect, useState } from 'react';
import { SIGN_IN_CHOICES, isSignInAs, loadSignInAs, saveSignInAs, type SignInAs } from '../lib/signin-as';

/** The "Sign in as" dropdown on the sign-in page. It chooses nothing about access: the Admin decides who may enter. */
export function SignInAsPicker() {
  const [choice, setChoice] = useState<SignInAs | ''>('');
  useEffect(() => { setChoice(loadSignInAs() ?? ''); }, []);
  return <label style={{ display: 'grid', gap: 6, margin: '0 0 16px', textAlign: 'left' }}>
    <span className="eyebrow">SIGN IN AS</span>
    <select value={choice} onChange={(event) => { const next = event.target.value; setChoice(isSignInAs(next) ? next : ''); saveSignInAs(isSignInAs(next) ? next : null); }} aria-label="Sign in as" style={{ padding: '12px 14px', borderRadius: 12, border: '1.5px solid var(--line, #d9e2e0)', background: 'transparent', color: 'inherit', font: 'inherit', width: '100%', boxSizing: 'border-box' }}>
      <option value="">Choose how you sign in…</option>
      {SIGN_IN_CHOICES.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
    </select>
    <small className="muted">You can only get in if the Admin has added your account.</small>
  </label>;
}
