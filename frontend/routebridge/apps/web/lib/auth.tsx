'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { API_BASE_URL, readError } from './api';
import { wakeServer } from './wake';

/**
 * RouteBridge's own sign-in. The API keeps the session in an httpOnly cookie that page scripts cannot read, so the website
 * only ever asks the API who is signed in (`/auth/session`) and calls it to sign in, sign up, sign out or reset a password.
 */
// remember: signed in with "Keep me signed in on this device" (the API keeps that session for days, and the page does not time it out)
export type SessionUser = { subject: string; email: string | null; name: string | null; startedAt: number; remember: boolean };
type SessionAnswer = { signed_in: boolean; subject?: string | null; email?: string | null; name?: string | null; started_at?: number | null; remember?: boolean };

type AuthState = {
  isLoaded: boolean;
  isSignedIn: boolean;
  user: SessionUser | null;
  refresh: () => Promise<void>;
  signOut: (options?: { redirectUrl?: string; everywhere?: boolean }) => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

function toUser(answer: SessionAnswer): SessionUser | null {
  if (!answer.signed_in || !answer.subject) return null;
  return { subject: answer.subject, email: answer.email ?? null, name: answer.name ?? null, startedAt: (answer.started_at ?? Date.now() / 1000) * 1000, remember: Boolean(answer.remember) };
}

async function call(path: string, body?: unknown): Promise<SessionAnswer> {
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    credentials: 'include',
    cache: 'no-store',
    headers: { 'Content-Type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!response.ok) throw await readError(response);
  return response.json();
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isLoaded, setLoaded] = useState(false);
  const [user, setUser] = useState<SessionUser | null>(null);
  const refresh = useCallback(async () => {
    try { setUser(toUser(await call('session'))); } catch { setUser(null); } finally { setLoaded(true); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const signOut = useCallback(async (options?: { redirectUrl?: string; everywhere?: boolean }) => {
    try { await call(`logout${options?.everywhere ? '?everywhere=true' : ''}`, {}); } catch { /* the cookie is cleared server-side when reachable; go on regardless */ }
    setUser(null);
    window.location.assign(options?.redirectUrl ?? '/');
  }, []);
  const value = useMemo<AuthState>(() => ({ isLoaded, isSignedIn: Boolean(user), user, refresh, signOut }), [isLoaded, user, refresh, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const state = useContext(AuthContext);
  if (!state) throw new Error('useAuth must be used inside <AuthProvider>');
  return state;
}

/** Wakes a sleeping backend first (free hosting), so the first person of the day does not lose their attempt to a 502. */
async function awake(onWaiting?: () => void) {
  await wakeServer(async () => (await fetch(`${API_BASE_URL}/api/v1/auth/providers`, { cache: 'no-store' })).status, { onWaiting });
}

export async function signIn(email: string, password: string, onWaiting?: () => void, remember = false) {
  await awake(onWaiting);
  return call('login', { email, password, remember });
}

export async function signUp(input: { email: string; password: string; full_name: string; phone: string; country: string; state: string; region: string }, onWaiting?: () => void) {
  await awake(onWaiting);
  return call('register', input);
}

export async function askPasswordReset(email: string) {
  await awake();
  return call('password/forgot', { email });
}

export async function resetPassword(token: string, password: string) {
  return call('password/reset', { token, password });
}

export type Providers = { google: boolean; password_reset: boolean; remember_days?: number };

/** Whether "Continue with Google" is offered. Waits for a sleeping backend first: asking too early used to hide the Google button. */
export async function getProviders(): Promise<Providers> {
  await awake();
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/providers`, { cache: 'no-store' });
  if (!response.ok) return { google: false, password_reset: false };
  return response.json();
}

/** Where "Continue with Google" goes: the API sends the browser to Google and back, then on to `next`. */
export function googleStartUrl(next: string, remember = false): string {
  return `${API_BASE_URL}/api/v1/auth/google/start?next=${encodeURIComponent(next)}${remember ? '&remember=true' : ''}`;
}

/** Only a path on this website, never another site. */
export function safeNext(raw: string | null | undefined): string {
  return raw && raw.startsWith('/') && !raw.startsWith('//') && !raw.includes('\\') ? raw : '/';
}
