import { describe, expect, it } from 'vitest';
import { buildMessage, idLabel, loadChoice, saveChoice } from './signup-role';

function fakeStore(initial: Record<string, string> = {}) {
  const data = { ...initial };
  return { getItem: (key: string) => data[key] ?? null, setItem: (key: string, value: string) => { data[key] = value; }, removeItem: (key: string) => { delete data[key]; }, data };
}

describe('sign-up role choice', () => {
  it('remembers a choice and gives it back', () => {
    const store = fakeStore();
    saveChoice({ role: 'merchant_user', shop: '  Ada Foods  ' }, store);
    expect(loadChoice(store)).toEqual({ role: 'merchant_user', shop: 'Ada Foods' });
    saveChoice({ role: 'driver' }, store);
    expect(loadChoice(store)).toEqual({ role: 'driver' });
    saveChoice(null, store);
    expect(loadChoice(store)).toBeNull();
  });

  it('ignores stored rubbish, unknown roles and a missing or blocked store', () => {
    expect(loadChoice(fakeStore({ rb_requested_role: 'not json' }))).toBeNull();
    expect(loadChoice(fakeStore({ rb_requested_role: JSON.stringify({ role: 'tenant_owner' }) }))).toBeNull();
    expect(loadChoice(fakeStore({ rb_requested_role: JSON.stringify({ role: 'driver', shop: 42 }) }))).toEqual({ role: 'driver' });
    expect(loadChoice(null)).toBeNull();
    expect(() => saveChoice({ role: 'driver' }, null)).not.toThrow();
    const blocked = { getItem: () => { throw new Error('blocked'); }, setItem: () => { throw new Error('blocked'); }, removeItem: () => { throw new Error('blocked'); } };
    expect(loadChoice(blocked)).toBeNull();
    expect(() => saveChoice({ role: 'driver' }, blocked)).not.toThrow();
  });

  it('calls the id a shop sign-up id for a shop and a user id for everyone else', () => {
    expect(idLabel('merchant_user')).toBe('Shop sign-up ID');
    expect(idLabel('driver')).toBe('User ID');
    expect(idLabel(null)).toBe('User ID');
  });

  it('writes a message the owner can act on', () => {
    const shop = buildMessage({ subject: 'user_abc123', email: 'a@b.ng', choice: { role: 'merchant_user', shop: 'Ada Foods' } });
    expect(shop).toContain('add my shop called Ada Foods');
    expect(shop).toContain('user_abc123 (a@b.ng)');
    expect(shop).toContain('Settings, then Merchants');
    const staff = buildMessage({ subject: 'user_abc123', choice: { role: 'driver' } });
    expect(staff).toContain('as Dispatcher');
    expect(staff).toContain('the Dispatchers screen');
    expect(buildMessage({ subject: 'user_abc123', choice: null })).toBe('Hello, please add me to RouteBridge. My user id is user_abc123.');
  });
});
