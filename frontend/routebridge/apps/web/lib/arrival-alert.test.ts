import { describe, expect, it } from 'vitest';
import { alertText, shouldAlert } from './arrival-alert';

describe('arrival alert', () => {
  it('fires only when the status changes into arrived or delivered', () => {
    expect(shouldAlert('en_route', 'arrived')).toBe(true);
    expect(shouldAlert('arrived', 'delivered')).toBe(true);
    expect(shouldAlert(null, 'arrived')).toBe(false); // first load of the page
    expect(shouldAlert('arrived', 'arrived')).toBe(false); // no change
    expect(shouldAlert('assigned', 'en_route')).toBe(false);
  });

  it('words the alert for the customer', () => {
    expect(alertText('arrived', 'Mama Put', 'MP-7')).toEqual({ title: 'Your rider has arrived', body: 'Mama Put: your rider is outside with order MP-7. Please be ready to receive it.' });
    expect(alertText('delivered', null, null).body).toBe('Your order was delivered. Thank you!');
  });
});
