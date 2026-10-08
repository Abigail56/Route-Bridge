import { describe, expect, it } from 'vitest';
import { callLink, smsLink, toInternational, whatsappLink } from './phone-links';

describe('phone links', () => {
  it('makes every common Nigerian format international', () => {
    for (const given of ['08031112222', '0803 111 2222', '+234 803 111 2222', '2348031112222', '8031112222', '00234 803 111 2222']) {
      expect(toInternational(given)).toBe('2348031112222');
    }
    expect(toInternational('+14155550123')).toBe('14155550123');
  });

  it('builds links with the message safely encoded', () => {
    const text = 'Code 482913 & thanks';
    expect(whatsappLink('08031112222', text)).toBe('https://wa.me/2348031112222?text=Code%20482913%20%26%20thanks');
    expect(smsLink('08031112222', text)).toContain('sms:+2348031112222');
    expect(smsLink('08031112222', text)).toContain('body=Code%20482913%20%26%20thanks');
    expect(callLink('0803 111 2222')).toBe('tel:+2348031112222');
  });
});
