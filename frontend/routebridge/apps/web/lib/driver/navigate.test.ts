import { describe, expect, it } from 'vitest';
import { navigationLinks } from './navigate';

describe('navigationLinks', () => {
  it('uses the pin when the job has one', () => {
    const links = navigationLinks({ latitude: 6.5244, longitude: 3.3792, address: '12 Allen Avenue' });
    expect(links.google).toContain('destination=6.5244,3.3792');
    expect(links.waze).toContain('ll=6.5244,3.3792');
    expect(links.apple).toContain('daddr=6.5244,3.3792');
  });

  it('falls back to the address text, safely encoded', () => {
    const links = navigationLinks({ latitude: null, longitude: null, address: '5 Bode Thomas & Sons, Surulere' });
    expect(links.google).toContain('query=5%20Bode%20Thomas%20%26%20Sons%2C%20Surulere');
    expect(links.waze).toContain('q=5%20Bode');
  });
});
