import { describe, expect, it } from 'vitest';
import { buildDriverLink, isLocalOnlyOrigin, validHours, whatsappLink } from './driver-access';

describe('driver access link', () => {
  it('puts the token after the # so it never travels to a server', () => {
    const link = buildDriverLink('https://app.example.com/', 'abc.def.ghi');
    expect(link).toBe('https://app.example.com/driver#token=abc.def.ghi');
    expect(new URL(link).search).toBe('');
    expect(new URLSearchParams(new URL(link).hash.slice(1)).get('token')).toBe('abc.def.ghi');
  });

  it('warns when the address only works on this computer', () => {
    expect(isLocalOnlyOrigin('http://localhost:3000')).toBe(true);
    expect(isLocalOnlyOrigin('http://127.0.0.1:3000')).toBe(true);
    expect(isLocalOnlyOrigin('https://routebridge.ng')).toBe(false);
    expect(isLocalOnlyOrigin('http://192.168.1.20:3000')).toBe(false);
  });

  it('builds a WhatsApp message to the driver for any way of writing a Nigerian number', () => {
    for (const phone of ['08031234567', '+2348031234567', '234 803 123 4567']) {
      const url = whatsappLink(phone, 'https://app.example.com/driver#token=t', 'Ada Okafor', 12);
      expect(url.startsWith('https://wa.me/2348031234567?text=')).toBe(true);
    }
    const text = decodeURIComponent(whatsappLink('08031234567', 'https://x/driver#token=t', 'Ada Okafor', 12).split('text=')[1]);
    expect(text).toContain('Hello Ada');
    expect(text).toContain('12 hours');
    expect(text).toContain('https://x/driver#token=t');
  });

  it('turns the token lifetime into whole hours', () => {
    expect(validHours(720 * 60)).toBe(12);
    expect(validHours(10)).toBe(1);
  });
});
