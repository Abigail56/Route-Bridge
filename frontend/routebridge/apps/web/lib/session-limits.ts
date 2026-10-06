/**
 * Fixed session time. Two limits, both counted from facts that survive a page refresh and other tabs:
 *  - a maximum session length, counted from when the person signed in (Clerk's session creation time), and
 *  - a quiet period: no mouse, keyboard or touch activity in any tab.
 * The person gets a warning one minute before either one ends.
 *
 * This is the app's own guard. The sign-in service (Clerk) keeps enforcing its own session lifetime in its dashboard too.
 */
export type SessionLimits = { maxMs: number; idleMs: number; warnMs: number };
export type SessionReason = 'idle' | 'max';
export type SessionState =
  | { status: 'ok' }
  | { status: 'warning'; reason: SessionReason; secondsLeft: number }
  | { status: 'expired'; reason: SessionReason };

const HOUR = 3_600_000;
const MINUTE = 60_000;

function positive(raw: string | undefined, fallback: number): number {
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

/** Defaults: 12 hours in total, 30 minutes of inactivity. Change them with NEXT_PUBLIC_SESSION_MAX_HOURS / NEXT_PUBLIC_SESSION_IDLE_MINUTES. */
export function sessionLimitsFromEnv(env: { max?: string; idle?: string } = { max: process.env.NEXT_PUBLIC_SESSION_MAX_HOURS, idle: process.env.NEXT_PUBLIC_SESSION_IDLE_MINUTES }): SessionLimits {
  return { maxMs: positive(env.max, 12) * HOUR, idleMs: positive(env.idle, 30) * MINUTE, warnMs: MINUTE };
}

export function evaluateSession(input: { now: number; startedAt: number; lastActivity: number } & SessionLimits): SessionState {
  const maxLeft = input.startedAt + input.maxMs - input.now;
  const idleLeft = input.lastActivity + input.idleMs - input.now;
  if (maxLeft <= 0) return { status: 'expired', reason: 'max' };
  if (idleLeft <= 0) return { status: 'expired', reason: 'idle' };
  const reason: SessionReason = maxLeft <= idleLeft ? 'max' : 'idle';
  const left = Math.min(maxLeft, idleLeft);
  return left <= input.warnMs ? { status: 'warning', reason, secondsLeft: Math.ceil(left / 1000) } : { status: 'ok' };
}

export function describeEnd(reason: SessionReason, limits: SessionLimits): string {
  if (reason === 'idle') return `You were signed out after ${Math.round(limits.idleMs / MINUTE)} minutes without activity, to keep your account safe.`;
  const hours = limits.maxMs / HOUR;
  return `Your ${Number.isInteger(hours) ? hours : hours.toFixed(1)}-hour session has ended. Please sign in again.`;
}
