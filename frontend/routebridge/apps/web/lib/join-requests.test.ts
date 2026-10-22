import { describe, expect, it } from 'vitest';
import { freshRequests, requestText, toSeen } from './join-requests';

const row = (id: string, sent_at = '2026-10-22T10:00:00Z') => ({ id, sent_at });

describe('join requests announced to the Admin', () => {
  it('stays quiet on the first look', () => {
    expect(freshRequests(null, [row('a')])).toEqual([]);
  });

  it('announces requests not seen before, and a request sent again', () => {
    const seen = toSeen([row('a'), row('b')]);
    expect(freshRequests(seen, [row('a'), row('b'), row('c')]).map((r) => r.id)).toEqual(['c']);
    expect(freshRequests(seen, [row('a', '2026-10-22T10:05:00Z'), row('b')]).map((r) => r.id)).toEqual(['a']);
    expect(freshRequests(seen, [row('b')])).toEqual([]);
  });

  it('names the shop or the person', () => {
    expect(requestText({ role: 'merchant_user', shop_name: 'Ada Foods', full_name: 'Ada', email: null })).toBe('Ada Foods wants to join as a shop');
    expect(requestText({ role: 'driver', shop_name: null, full_name: 'Musa Bello', email: 'm@x.test' })).toBe('Musa Bello wants to join as a driver');
    expect(requestText({ role: 'merchant_user', shop_name: null, full_name: null, email: 'shop@x.test' })).toBe('shop@x.test wants to join as a shop');
  });
});
