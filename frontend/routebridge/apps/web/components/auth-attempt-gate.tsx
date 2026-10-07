'use client';

import { SignIn, SignUp } from '@clerk/nextjs';
import { usePathname } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import { describeEnd, sessionLimitsFromEnv } from '../lib/session-limits';
import { createApiClient, friendlyMessage } from '../lib/api';

export function AuthAttemptGate({ mode }: { mode: 'signin' | 'signup' }) {
  const [identifier, setIdentifier] = useState('');
  // Clerk walks through sub-pages (/sign-in/factor-one, /sign-up/verify-email-address…); once there, the attempt check already passed.
  const pathname = usePathname() ?? '';
  const [allowed, setAllowed] = useState(false);
  const insideFlow = pathname.replace(/\/+$/, '') !== (mode === 'signin' ? '/sign-in' : '/sign-up');
  const [error, setError] = useState('');
  const [endedNote, setEndedNote] = useState('');
  // After the fixed session time (or a long quiet period) the person lands here with the reason in the address.
  useEffect(() => {
    const reason = new URLSearchParams(window.location.search).get('reason');
    if (reason === 'idle' || reason === 'max') setEndedNote(describeEnd(reason, sessionLimitsFromEnv()));
  }, []);
  // The attempt endpoint is public (the user is not signed in yet), so no token is sent.
  const api = useMemo(() => createApiClient(async () => null), []);
  async function continueToClerk() {
    setError('');
    try {
      await api.authAttempt(mode, identifier);
      setAllowed(true);
    } catch (exc) {
      setError(friendlyMessage(exc));
    }
  }
  const appearance = { variables: { colorPrimary: '#2563eb', borderRadius: '12px', fontFamily: 'Plus Jakarta Sans, sans-serif', fontSize: '16px' } };
  if (allowed || insideFlow) return <AuthShell>{mode === 'signin' ? <SignIn routing="path" path="/sign-in" appearance={appearance} /> : <SignUp routing="path" path="/sign-up" appearance={appearance} />}</AuthShell>;
  return <AuthShell><section className="auth-gate"><h1>{mode === 'signin' ? 'Sign in to RouteBridge' : 'Create your RouteBridge account'}</h1>{endedNote && <p role="status" className="auth-note">{endedNote}</p>}<p>Welcome. Tell us who you are and we&apos;ll take you right in. (We allow a few attempts at a time to keep your account safe.)</p><input value={identifier} onChange={(event) => setIdentifier(event.target.value)} placeholder="Email or phone" aria-label="Email or phone" /><button onClick={continueToClerk} disabled={!identifier.trim()}>Continue</button>{error && <p role="alert">{error}</p>}</section></AuthShell>;
}

function AuthShell({ children }: { children: React.ReactNode }) {
  const hour = new Date().getHours();
  const greeting = hour >= 5 && hour < 12 ? 'Good morning' : hour >= 12 && hour < 17 ? 'Good afternoon' : 'Good evening';
  return (
    <main className="auth-split">
      <aside className="auth-hero">
        <div className="auth-hero-brand"><span className="brand-mark" role="img" aria-label="RouteBridge logo" /><strong>RouteBridge</strong></div>
        <div className="auth-hero-copy">
          <span className="auth-pill">{greeting}, and welcome</span>
          <h2>Where life is made easy, one doorstep at a time.</h2>
          <p>From the first pickup to the last handshake, RouteBridge keeps your riders, merchants and customers on the same page, so your day runs smoother and your customers smile more.</p>
          <ul><li>See every delivery live, from pickup to doorstep</li><li>Reach customers in the language they trust</li><li>Close the day with cash that adds up</li></ul>
        </div>
        <svg className="auth-routes" viewBox="0 0 600 300" aria-hidden="true"><path id="auth-route" d="M20 250 C140 120 220 260 330 150 S520 60 580 40" /><circle cx="20" cy="250" r="8" /><circle cx="330" cy="150" r="8" /><circle className="end" cx="580" cy="40" r="10" /><circle className="dot" r="7"><animateMotion dur="8s" repeatCount="indefinite" path="M20 250 C140 120 220 260 330 150 S520 60 580 40" /></circle></svg>
        <div className="auth-chip one" aria-hidden="true"><b>Live</b><span>tracking for every parcel</span></div>
        <div className="auth-chip two" aria-hidden="true"><b>100%</b><span>cash accounted for</span></div>
        <p className="auth-credit">Photo: Clara Sanchiz, <a href="https://commons.wikimedia.org/wiki/File:Lagos_skyline.jpg" target="_blank" rel="noreferrer">Lagos skyline</a>, CC BY-SA 2.0</p>
      </aside>
      <div className="auth-panel">{children}</div>
    </main>
  );
}
