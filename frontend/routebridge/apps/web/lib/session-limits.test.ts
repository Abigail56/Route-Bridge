import { describe, expect, it } from 'vitest';
import { describeEnd, evaluateSession, sessionLimitsFromEnv } from './session-limits';

const limits = { maxMs: 12 * 3_600_000, idleMs: 30 * 60_000, warnMs: 60_000 };
const start = 1_000_000_000_000;

describe('fixed session time', () => {
  it('defaults to 12 hours in total and 30 minutes of quiet, and can be configured', () => {
    expect(sessionLimitsFromEnv({})).toEqual(limits);
    expect(sessionLimitsFromEnv({ max: '8', idle: '15' })).toEqual({ maxMs: 8 * 3_600_000, idleMs: 15 * 60_000, warnMs: 60_000 });
    expect(sessionLimitsFromEnv({ max: 'abc', idle: '-5' })).toEqual(limits);
  });

  it('is fine while the person is active', () => {
    expect(evaluateSession({ now: start + 60_000, startedAt: start, lastActivity: start + 59_000, ...limits })).toEqual({ status: 'ok' });
  });

  it('warns a minute before the quiet period ends, then signs out', () => {
    const active = start + 3_600_000;
    expect(evaluateSession({ now: active + 29 * 60_000 + 30_000, startedAt: start, lastActivity: active, ...limits })).toEqual({ status: 'warning', reason: 'idle', secondsLeft: 30 });
    expect(evaluateSession({ now: active + 30 * 60_000, startedAt: start, lastActivity: active, ...limits })).toEqual({ status: 'expired', reason: 'idle' });
  });

  it('ends the session at the fixed maximum even if the person is busy', () => {
    const busy = start + limits.maxMs - 10_000;
    expect(evaluateSession({ now: start + limits.maxMs - 10_000, startedAt: start, lastActivity: busy, ...limits })).toEqual({ status: 'warning', reason: 'max', secondsLeft: 10 });
    expect(evaluateSession({ now: start + limits.maxMs, startedAt: start, lastActivity: start + limits.maxMs, ...limits })).toEqual({ status: 'expired', reason: 'max' });
  });

  it('says why the person was signed out', () => {
    expect(describeEnd('idle', limits)).toContain('30 minutes');
    expect(describeEnd('max', limits)).toContain('12-hour');
  });
});
