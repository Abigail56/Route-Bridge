'use client';

import { useClerk, useSession } from '@clerk/nextjs';
import { usePathname } from 'next/navigation';
import { useEffect, useMemo, useRef, useState } from 'react';
import { evaluateSession, sessionLimitsFromEnv, type SessionReason } from '../lib/session-limits';

const KEY = 'rb-last-activity';
const PUBLIC_PREFIXES = ['/sign-in', '/sign-up', '/track', '/driver'];

function readActivity(): number {
  try { return Number(window.localStorage.getItem(KEY)) || Date.now(); } catch { return Date.now(); }
}
function writeActivity(value: number) {
  try { window.localStorage.setItem(KEY, String(value)); } catch { /* storage blocked: this tab still tracks its own activity */ }
}

/** Signs people out when their session reaches the fixed time limit or they have been away too long, with a warning first. */
export function SessionGuard() {
  const { isLoaded, isSignedIn, session } = useSession();
  const { signOut } = useClerk();
  const pathname = usePathname() ?? '/';
  const limits = useMemo(() => sessionLimitsFromEnv(), []);
  const lastActivity = useRef(0);
  const [warning, setWarning] = useState<{ reason: SessionReason; secondsLeft: number } | null>(null);
  const active = isLoaded && isSignedIn && Boolean(session) && !PUBLIC_PREFIXES.some((prefix) => pathname.startsWith(prefix));

  useEffect(() => {
    if (!active) return;
    lastActivity.current = readActivity();
    let lastWrite = 0;
    const touch = () => {
      const now = Date.now();
      lastActivity.current = now;
      if (now - lastWrite > 5000) { lastWrite = now; writeActivity(now); }  // shared with other tabs
    };
    const events = ['mousemove', 'mousedown', 'keydown', 'touchstart', 'scroll', 'click'] as const;
    events.forEach((name) => window.addEventListener(name, touch, { passive: true }));
    const onStorage = (event: StorageEvent) => { if (event.key === KEY && event.newValue) lastActivity.current = Math.max(lastActivity.current, Number(event.newValue)); };
    window.addEventListener('storage', onStorage);
    touch();

    const check = () => {
      const startedAt = session?.createdAt ? new Date(session.createdAt).getTime() : Date.now();
      const state = evaluateSession({ now: Date.now(), startedAt, lastActivity: Math.max(lastActivity.current, readActivity()), ...limits });
      if (state.status === 'expired') { void signOut({ redirectUrl: `/sign-in?reason=${state.reason}` }); return; }
      setWarning(state.status === 'warning' ? { reason: state.reason, secondsLeft: state.secondsLeft } : null);
    };
    check();
    const timer = setInterval(check, 5000);
    return () => { clearInterval(timer); events.forEach((name) => window.removeEventListener(name, touch)); window.removeEventListener('storage', onStorage); };
  }, [active, session, limits, signOut]);

  if (!active || !warning) return null;
  return <div className="session-warning" role="alertdialog" aria-live="assertive" aria-label="Session about to end">
    <div>
      <b>{warning.reason === 'idle' ? 'Still there?' : 'Your session is about to end'}</b>
      <span>You will be signed out in {warning.secondsLeft} second{warning.secondsLeft === 1 ? '' : 's'}{warning.reason === 'idle' ? ' because you have been away.' : ' because it reached its time limit.'}</span>
    </div>
    {warning.reason === 'idle'
      ? <button className="button primary" onClick={() => { const now = Date.now(); lastActivity.current = now; writeActivity(now); setWarning(null); }}>Stay signed in</button>
      : <button className="button secondary" onClick={() => void signOut({ redirectUrl: '/sign-in?reason=max' })}>Sign out now</button>}
  </div>;
}
