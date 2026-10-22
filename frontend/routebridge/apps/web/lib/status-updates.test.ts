import { describe, expect, it } from 'vitest';
import { changeText, newOrders, statusChanges, toSnapshot } from './status-updates';

const row = (id: string, status: string, extra: Record<string, unknown> = {}) => ({ id, external_ref: `REF-${id}`, status, ...extra });

describe('status changes shown to the shop', () => {
  it('says nothing on the first look or for orders that did not change', () => {
    expect(statusChanges(null, [row('1', 'pending')])).toEqual([]);
    const before = toSnapshot([row('1', 'pending'), row('2', 'en_route')]);
    expect(statusChanges(before, [row('1', 'pending'), row('2', 'en_route')])).toEqual([]);
  });

  it('reports each order that moved, in plain words', () => {
    const before = toSnapshot([row('1', 'pending'), row('2', 'assigned'), row('3', 'accepted'), row('4', 'en_route')]);
    const found = statusChanges(before, [row('1', 'assigned'), row('2', 'accepted'), row('3', 'en_route'), row('4', 'arrived')]);
    expect(found.map((change) => change.text)).toEqual([
      'Order REF-1 was given to a rider',
      'The rider accepted order REF-2',
      'Order REF-3 is on the way',
      "The rider is at the customer's door with order REF-4",
    ]);
  });

  it('tells the shop when the customer\'s code was checked on delivery', () => {
    const before = toSnapshot([row('1', 'arrived')]);
    const [change] = statusChanges(before, [row('1', 'delivered', { code_verified: true })]);
    expect(change.text).toContain("customer's code was checked");
    expect(change.tone).toBe('good');
    expect(changeText('X', 'delivered', false).text).toBe('Order X was delivered');
  });

  it('ignores orders that were not on the screen before and flags problems as warnings', () => {
    const before = toSnapshot([row('1', 'arrived')]);
    expect(statusChanges(before, [row('1', 'arrived'), row('9', 'pending')])).toEqual([]);
    expect(statusChanges(before, [row('1', 'failed_attempt')])[0].tone).toBe('warn');
    expect(changeText('X', 'something_new').text).toBe('Order X changed to something new');
  });
});

describe('new orders announced to the Admin', () => {
  it('announces nothing on the first look, so opening the console does not chime for old orders', () => {
    expect(newOrders(null, [row('1', 'pending')])).toEqual([]);
  });

  it('announces each order that was not there before, with the shop name when known', () => {
    const before = toSnapshot([row('1', 'pending')]);
    const found = newOrders(before, [row('1', 'assigned'), row('2', 'pending', { merchant: 'Ada Stores' }), row('3', 'pending')]);
    expect(found.map((change) => change.text)).toEqual(['New order REF-2 from Ada Stores', 'New order REF-3']);
    expect(found.every((change) => change.tone === 'info')).toBe(true);
  });

  it('stays quiet when nothing new arrived', () => {
    const before = toSnapshot([row('1', 'pending'), row('2', 'en_route')]);
    expect(newOrders(before, [row('1', 'assigned'), row('2', 'arrived')])).toEqual([]);
  });
});
