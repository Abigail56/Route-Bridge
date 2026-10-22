import { describe, expect, it } from 'vitest';
import { alertsGrew } from './alert-sound';

describe('alert sound for new notifications', () => {
  it('stays quiet when the console first opens', () => {
    expect(alertsGrew(null, { unassigned: 3 })).toBe(false);
  });

  it('sounds for a new kind of notification or a higher count', () => {
    expect(alertsGrew({ unassigned: 1 }, { unassigned: 1, code: 1 })).toBe(true);
    expect(alertsGrew({ problems: 1 }, { problems: 2 })).toBe(true);
  });

  it('stays quiet when nothing grew', () => {
    expect(alertsGrew({ unassigned: 2, exceptions: 1 }, { unassigned: 1, exceptions: 1 })).toBe(false);
    expect(alertsGrew({ unassigned: 2 }, {})).toBe(false);
  });
});
