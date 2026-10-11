import { describe, expect, it, vi } from 'vitest';
import { isGatewayError, wakeServer } from './wake';

const instant = () => Promise.resolve();

describe('waking a sleeping backend', () => {
  it('recognises the "behind this server nothing answered" errors only', () => {
    expect([502, 503, 504].every(isGatewayError)).toBe(true);
    expect([200, 401, 403, 404, 429, 500].some(isGatewayError)).toBe(false);
  });

  it('returns at once, and says nothing, when the backend is already awake (a 401 counts as awake)', async () => {
    const onWaiting = vi.fn();
    const probe = vi.fn().mockResolvedValue(401);
    expect(await wakeServer(probe, { onWaiting, sleep: instant })).toBe(true);
    expect(probe).toHaveBeenCalledTimes(1);
    expect(onWaiting).not.toHaveBeenCalled();
  });

  it('tells the person once, keeps trying, and stops as soon as the backend answers', async () => {
    const onWaiting = vi.fn();
    const probe = vi.fn().mockResolvedValueOnce(502).mockResolvedValueOnce(504).mockResolvedValueOnce(502).mockResolvedValueOnce(200);
    const sleep = vi.fn().mockResolvedValue(undefined);
    expect(await wakeServer(probe, { onWaiting, sleep, gapMs: 5000 })).toBe(true);
    expect(probe).toHaveBeenCalledTimes(4);
    expect(onWaiting).toHaveBeenCalledTimes(1);
    expect(sleep).toHaveBeenCalledTimes(3);
    expect(sleep).toHaveBeenCalledWith(5000);
  });

  it('treats a dropped connection like a sleeping server', async () => {
    const probe = vi.fn().mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce(401);
    expect(await wakeServer(probe, { sleep: instant })).toBe(true);
    expect(probe).toHaveBeenCalledTimes(2);
  });

  it('gives up after the last try and says so, instead of waiting for ever', async () => {
    const probe = vi.fn().mockResolvedValue(502);
    expect(await wakeServer(probe, { sleep: instant, tries: 4 })).toBe(false);
    expect(probe).toHaveBeenCalledTimes(4);
  });
});
