import { describe, expect, it } from 'vitest';
import { pushSupported, urlBase64ToUint8Array } from './push';

describe('driver push helpers', () => {
  it('turns the server key (url-safe base64, no padding) into bytes', () => {
    // 0xfb 0xff 0xfe encodes to "-__-" in url-safe base64
    expect(Array.from(urlBase64ToUint8Array('-__-'))).toEqual([0xfb, 0xff, 0xfe]);
    expect(Array.from(urlBase64ToUint8Array('AQID'))).toEqual([1, 2, 3]);
    expect(Array.from(urlBase64ToUint8Array('AQI'))).toEqual([1, 2]); // padding is restored
  });

  it('reports no support outside a browser', () => {
    expect(pushSupported()).toBe(false);
  });
});
