'use client';

import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { friendlyMessage } from '../lib/api';
import { askPasswordReset, getProviders, googleStartUrl, resetPassword, safeNext, signIn, signUp, type Providers } from '../lib/auth';
import { describeEnd, sessionLimitsFromEnv } from '../lib/session-limits';
import { EMPTY_PLACE, PlaceFields, type Place } from './place-fields';

type PasswordProps = { value: string; onChange: (value: string) => void; autoComplete: 'current-password' | 'new-password'; minLength?: number; maxLength?: number; describedBy?: string };

/** A password box with a Show / Hide button, so people can check what they typed and hide it again. */
function PasswordInput({ value, onChange, autoComplete, minLength, maxLength, describedBy }: PasswordProps) {
  const [shown, setShown] = useState(false);
  return <span className="pw-field">
    <input type={shown ? 'text' : 'password'} value={value} onChange={(event) => onChange(event.target.value)} required minLength={minLength} maxLength={maxLength} autoComplete={autoComplete} aria-describedby={describedBy} autoCapitalize="off" autoCorrect="off" spellCheck={false} />
    <button type="button" className="pw-toggle" onClick={() => setShown((value) => !value)} aria-pressed={shown} aria-label={shown ? 'Hide password' : 'Show password'}>
      <svg viewBox="0 0 24 24" aria-hidden="true">{shown
        ? <><path d="M3 3l18 18" /><path d="M10.6 5.1A10 10 0 0 1 12 5c6 0 9.5 7 9.5 7a17 17 0 0 1-3.2 4.1M6.6 6.6A17 17 0 0 0 2.5 12S6 19 12 19a9.6 9.6 0 0 0 5.4-1.6" /><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" /></>
        : <><path d="M2.5 12S6 5 12 5s9.5 7 9.5 7-3.5 7-9.5 7S2.5 12 2.5 12Z" /><circle cx="12" cy="12" r="3" /></>}</svg>
      <span>{shown ? 'Hide' : 'Show'}</span>
    </button>
  </span>;
}

// what ?error= on /sign-in means (the API sends people back here when the Google round trip did not work)
const GOOGLE_ERRORS: Record<string, string> = {
  google_cancelled: 'Google sign-in was cancelled. Try again, or use your email and password.',
  google_expired: 'That Google sign-in took too long or was opened in another browser. Please try again.',
  google_failed: 'Google sign-in did not work just now. Please try again in a moment.',
  google_unverified: 'Google has not verified that email address yet, so we cannot use it to sign you in.',
  google_off: 'Google sign-in is not set up on this server. Use your email and password.',
  deactivated: 'This account has been deactivated. Contact the person who runs your company on RouteBridge.',
};

function query(name: string): string | null {
  return typeof window === 'undefined' ? null : new URLSearchParams(window.location.search).get(name);
}

function useProviders(): Providers | null {
  const [providers, setProviders] = useState<Providers | null>(null);
  useEffect(() => { getProviders().then(setProviders).catch(() => setProviders({ google: false, password_reset: false })); }, []);
  return providers;
}

function GoogleButton({ next, label }: { next: string; label: string }) {
  return <a className="auth-google" href={googleStartUrl(next)}>
    <svg viewBox="0 0 48 48" aria-hidden="true" width="20" height="20"><path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.6 5.4 2.6 13.2l7.9 6.2C12.4 13.6 17.7 9.5 24 9.5z" /><path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.7 6c4.5-4.2 6.9-10.3 6.9-17.7z" /><path fill="#FBBC05" d="M10.5 28.6c-.5-1.4-.8-3-.8-4.6s.3-3.2.8-4.6l-7.9-6.2C1 16.5 0 20.1 0 24s1 7.5 2.6 10.8l7.9-6.2z" /><path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.7-6c-2.2 1.5-5 2.3-8.2 2.3-6.3 0-11.6-4.1-13.5-9.8l-7.9 6.2C6.6 42.6 14.6 48 24 48z" /></svg>
    {label}
  </a>;
}

function Divider() {
  return <div className="auth-divider" role="separator"><span>or</span></div>;
}

export function SignInForm() {
  const providers = useProviders();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [waking, setWaking] = useState(false); // free hosting: the backend may be asleep and needs up to a minute
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const [next, setNext] = useState('/');
  // after the fixed session time (or a long quiet period) the person lands here with the reason in the address
  useEffect(() => {
    const reason = query('reason');
    if (reason === 'idle' || reason === 'max') setNote(describeEnd(reason, sessionLimitsFromEnv()));
    const problem = query('error');
    if (problem && GOOGLE_ERRORS[problem]) setError(GOOGLE_ERRORS[problem]);
    setNext(safeNext(query('next')));
  }, []);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError('');
    try {
      await signIn(email.trim(), password, () => setWaking(true));
      window.location.assign(next); // a full load, so every part of the site sees the new session
    } catch (exc) { setError(friendlyMessage(exc)); setBusy(false); } finally { setWaking(false); }
  }
  return <AuthShell>
    <section className="auth-gate">
      <h1>Sign in to RouteBridge</h1>
      {note && <p role="status" className="auth-note">{note}</p>}
      {waking && <p role="status" className="auth-note">Waking up the server. This can take up to a minute the first time. Please wait…</p>}
      {providers?.google && <><GoogleButton next={next} label="Continue with Google" /><Divider /></>}
      <form onSubmit={submit} className="auth-form">
        <label>Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="email" inputMode="email" /></label>
        <label>Password<PasswordInput value={password} onChange={setPassword} autoComplete="current-password" /></label>
        {providers?.password_reset && <a className="auth-link auth-forgot" href="/forgot-password">Forgot password?</a>}
        <button type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
      </form>
      {error && <p role="alert">{error}</p>}
      <p className="auth-switch">New to RouteBridge? <a className="auth-link" href="/sign-up">Create an account</a></p>
    </section>
  </AuthShell>;
}

export function SignUpForm() {
  const providers = useProviders();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [place, setPlace] = useState<Place>(EMPTY_PLACE);
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [waking, setWaking] = useState(false);
  const [error, setError] = useState('');
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (password !== confirm) { setError('The two passwords are not the same.'); return; }
    setBusy(true); setError('');
    try {
      await signUp({ full_name: name.trim(), email: email.trim(), password, phone: place.phone.trim(), country: place.country, state: place.state.trim(), region: place.region.trim() }, () => setWaking(true));
      window.location.assign('/'); // the "not linked yet" screen with their ID to send the owner
    } catch (exc) { setError(friendlyMessage(exc)); setBusy(false); } finally { setWaking(false); }
  }
  return <AuthShell>
    <section className="auth-gate">
      <h1>Create your RouteBridge account</h1>
      {waking && <p role="status" className="auth-note">Waking up the server. This can take up to a minute the first time. Please wait…</p>}
      {providers?.google && <><GoogleButton next="/" label="Sign up with Google" /><Divider /></>}
      <form onSubmit={submit} className="auth-form">
        <label>Full name<input value={name} onChange={(event) => setName(event.target.value)} required minLength={2} maxLength={200} autoComplete="name" /></label>
        <label>Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="email" inputMode="email" /></label>
        <PlaceFields value={place} onChange={setPlace} />
        <label>Password<PasswordInput value={password} onChange={setPassword} minLength={8} maxLength={128} autoComplete="new-password" describedBy="password-hint" /></label>
        <small id="password-hint" className="auth-hint">At least 8 characters. A short sentence is easy to remember and hard to guess.</small>
        <label>Confirm password<PasswordInput value={confirm} onChange={setConfirm} minLength={8} maxLength={128} autoComplete="new-password" /></label>
        <button type="submit" disabled={busy}>{busy ? 'Creating your account…' : 'Create account'}</button>
      </form>
      {error && <p role="alert">{error}</p>}
      <p className="auth-switch">Already have an account? <a className="auth-link" href="/sign-in">Sign in</a></p>
    </section>
  </AuthShell>;
}

export function ForgotPasswordForm() {
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError('');
    try { await askPasswordReset(email.trim()); setSent(true); } catch (exc) { setError(friendlyMessage(exc)); } finally { setBusy(false); }
  }
  return <AuthShell>
    <section className="auth-gate">
      <h1>Reset your password</h1>
      {sent
        ? <p role="status" className="auth-note">If an account exists for {email.trim()}, we have emailed it a link. It works for 30 minutes. Check your spam folder too.</p>
        : <form onSubmit={submit} className="auth-form">
            <p>Enter the email you signed up with and we will send you a link to choose a new password.</p>
            <label>Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="email" inputMode="email" /></label>
            <button type="submit" disabled={busy}>{busy ? 'Sending…' : 'Email me a reset link'}</button>
          </form>}
      {error && <p role="alert">{error}</p>}
      <p className="auth-switch"><a className="auth-link" href="/sign-in">Back to sign in</a></p>
    </section>
  </AuthShell>;
}

export function ResetPasswordForm() {
  const [token, setToken] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  // the token travels after # so it never reaches server logs or other sites; read it, then take it out of the address bar
  useEffect(() => {
    const found = new URLSearchParams(window.location.hash.slice(1)).get('token') ?? '';
    setToken(found);
    if (found) window.history.replaceState(null, '', window.location.pathname);
  }, []);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError('');
    try { await resetPassword(token, password); window.location.assign('/'); } catch (exc) { setError(friendlyMessage(exc)); setBusy(false); }
  }
  return <AuthShell>
    <section className="auth-gate">
      <h1>Choose a new password</h1>
      {!token
        ? <p role="alert">This page needs the link from your reset email. <a className="auth-link" href="/forgot-password">Ask for a new link</a>.</p>
        : <form onSubmit={submit} className="auth-form">
            <label>New password<PasswordInput value={password} onChange={setPassword} minLength={8} maxLength={128} autoComplete="new-password" /></label>
            <small className="auth-hint">At least 8 characters. Every other device signed in to your account will be signed out.</small>
            <button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save and sign in'}</button>
          </form>}
      {error && <p role="alert">{error}</p>}
    </section>
  </AuthShell>;
}

export function AuthShell({ children }: { children: ReactNode }) {
  // The greeting depends on the visitor's clock, but the server builds this page in its own time zone (UTC on Render and inside Docker).
  // Deciding it while rendering made the server's page differ from the browser's and React threw hydration errors (#425, #418, #423),
  // so the first paint says "Welcome" on both sides and the browser fills in the right greeting once the page has loaded.
  const [greeting, setGreeting] = useState('Welcome');
  useEffect(() => {
    const hour = new Date().getHours();
    setGreeting(hour >= 5 && hour < 12 ? 'Good morning, and welcome' : hour >= 12 && hour < 17 ? 'Good afternoon, and welcome' : 'Good evening, and welcome');
  }, []);
  return (
    <main className="auth-split">
      <aside className="auth-hero">
        <a className="auth-hero-brand" href="/"><span className="brand-mark" role="img" aria-label="RouteBridge Logistics logo" /><strong>RouteBridge Logistics</strong></a>
        <div className="auth-hero-copy">
          <span className="auth-pill">{greeting}</span>
          <h2>Making every delivery easier, one doorstep at a time.</h2>
          <p>From the first pickup to the final handoff, RouteBridge Logistics keeps your dispatchers, riders, merchants, and customers connected - so your operations run smoothly and every delivery is easier to manage.</p>
          <ul>
            <li>Track every delivery live, from pickup to doorstep</li>
            <li>Keep customers informed through trusted channels</li>
            <li>Close the day with every payment reconciled</li>
          </ul>
        </div>
      </aside>
      <div className="auth-panel">{children}</div>
    </main>
  );
}
