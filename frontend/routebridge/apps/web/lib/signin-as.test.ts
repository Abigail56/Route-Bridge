import { describe, expect, it } from 'vitest';
import { doorOf, loadSignInAs, mismatchMessage, saveSignInAs } from './signin-as';

const fakeStore = (initial: Record<string, string> = {}) => {
  const data = { ...initial };
  return { getItem: (k: string) => data[k] ?? null, setItem: (k: string, v: string) => { data[k] = v; }, removeItem: (k: string) => { delete data[k]; } };
};

describe('sign in as', () => {
  it('maps every role to a door', () => {
    expect(doorOf('tenant_owner')).toBe('admin');
    expect(doorOf('finance')).toBe('admin');
    expect(doorOf('merchant_user')).toBe('merchant');
    expect(doorOf('driver')).toBe('dispatcher');
  });
  it('stays quiet when the choice matches or nothing was chosen', () => {
    expect(mismatchMessage('admin', 'tenant_owner')).toBeNull();
    expect(mismatchMessage(null, 'driver')).toBeNull();
    expect(mismatchMessage('merchant', null)).toBeNull();
  });
  it('says plainly when the choice and the account disagree', () => {
    expect(mismatchMessage('merchant', 'tenant_owner')).toContain('added by the Admin as an Admin');
    expect(mismatchMessage('admin', 'driver')).toContain('as a Dispatcher');
  });
  it('remembers the choice and ignores junk or blocked storage', () => {
    const store = fakeStore();
    saveSignInAs('dispatcher', store);
    expect(loadSignInAs(store)).toBe('dispatcher');
    expect(loadSignInAs(fakeStore({ rb_signin_as: 'wizard' }))).toBeNull();
    expect(() => saveSignInAs('admin', null)).not.toThrow();
    saveSignInAs(null, store);
    expect(loadSignInAs(store)).toBeNull();
  });
});
