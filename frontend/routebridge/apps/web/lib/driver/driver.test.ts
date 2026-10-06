import 'fake-indexeddb/auto';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DriverApiError, parseDriverToken, type DriverClient } from './api';
import { enqueue, enqueueLocation, loadPhoto, queueSize, readQueue, type SyncEvent } from './queue';
import { allRecords, clearAll, seal, secureGet, secureSet, unseal } from './store';
import { backoffMs, syncOnce } from './sync';

const JOB = '11111111-1111-4111-8111-111111111111';
const DRIVER = '22222222-2222-4222-8222-222222222222';

function event(type: SyncEvent['event_type'], payload: Record<string, unknown> = {}, id = crypto.randomUUID()): SyncEvent {
  return { event_id: id, device_id: 'test-device', event_type: type, aggregate_type: type === 'driver.location' ? 'driver' : 'delivery_job', aggregate_id: type === 'driver.location' ? DRIVER : JOB, payload, occurred_at: new Date().toISOString() };
}

/** Fake server client; `respond` decides per-event outcomes. */
function fakeClient(respond: (events: SyncEvent[]) => { accepted?: string[]; duplicate?: string[]; rejected?: string[] } | Error) {
  const sync = vi.fn(async (events: SyncEvent[]) => {
    const out = respond(events);
    if (out instanceof Error) throw out;
    return { accepted_event_ids: out.accepted ?? [], duplicate_event_ids: out.duplicate ?? [], rejected_event_ids: out.rejected ?? [] };
  });
  const requestUpload = vi.fn(async () => ({ upload_url: 'https://up.test/x', method: 'PUT' as const, headers: { 'Content-Type': 'image/jpeg' }, object_url: 'media://t/j/photo-1.jpg', max_bytes: 1, needs_auth: false }));
  const putUpload = vi.fn(async () => undefined);
  return { client: { sync, requestUpload, putUpload } as unknown as DriverClient, sync, requestUpload, putUpload };
}
const acceptAll = (events: SyncEvent[]) => ({ accepted: events.map((e) => e.event_id) });

beforeEach(async () => { await clearAll(); });

describe('encrypted store', () => {
  it('round-trips data and never stores plaintext', async () => {
    const plain = new TextEncoder().encode('secret-token-value');
    const sealed = await seal(plain);
    expect(new TextDecoder().decode(await unseal(sealed))).toBe('secret-token-value');
    expect(Buffer.from(sealed.data).includes(Buffer.from('secret-token'))).toBe(false);
    const other = await seal(plain);
    expect(Buffer.from(other.iv).equals(Buffer.from(sealed.iv))).toBe(false); // fresh IV every time
  });

  it('detects tampering', async () => {
    const sealed = await seal(new TextEncoder().encode('hello'));
    const bytes = new Uint8Array(sealed.data);
    bytes[0] ^= 0xff;
    await expect(unseal({ iv: sealed.iv, data: bytes.buffer })).rejects.toBeTruthy();
  });

  it('secureSet/secureGet persist encrypted values', async () => {
    await secureSet('session', { token: 'abc.def.ghi' });
    expect(await secureGet('session')).toEqual({ token: 'abc.def.ghi' });
    expect(await secureGet('missing')).toBeUndefined();
  });
});

describe('queue', () => {
  it('keeps events in the order they happened and encrypts them at rest', async () => {
    await enqueue(event('delivery.transition', { target_status: 'accepted' }));
    await enqueue(event('delivery.transition', { target_status: 'en_route' }));
    await enqueue(event('delivery.transition', { target_status: 'arrived' }));
    expect((await readQueue()).map((q) => q.item.event.payload.target_status)).toEqual(['accepted', 'en_route', 'arrived']);
    const raw = JSON.stringify(Array.from((await allRecords<{ sealed: { data: ArrayBuffer } }>('queue')).map((r) => Array.from(new Uint8Array(r.sealed.data)))));
    expect(raw.includes('en_route')).toBe(false);
  });

  it('keeps only the newest GPS ping', async () => {
    await enqueue(event('delivery.transition', { target_status: 'accepted' }));
    await enqueueLocation(event('driver.location', { latitude: 1, longitude: 1 }));
    await enqueueLocation(event('driver.location', { latitude: 2, longitude: 2 }));
    const kinds = (await readQueue()).map((q) => q.item.event.event_type);
    expect(kinds).toEqual(['delivery.transition', 'driver.location']);
    expect((await readQueue())[1].item.event.payload.latitude).toBe(2);
  });

  it('stores photos encrypted and returns them intact', async () => {
    const photo = new Blob([new Uint8Array([0xff, 0xd8, 0xff, 1, 2, 3, 4])], { type: 'image/jpeg' });
    await enqueue(event('delivery.proof', { recipient_name: 'Ada' }), photo);
    const [{ item }] = await readQueue();
    const back = await loadPhoto(item.photoId as string);
    expect(back?.type).toBe('image/jpeg');
    expect(Array.from(new Uint8Array(await back!.arrayBuffer()))).toEqual([0xff, 0xd8, 0xff, 1, 2, 3, 4]);
    const stored = await allRecords<{ sealed: { data: ArrayBuffer } }>('blobs');
    expect(Array.from(new Uint8Array(stored[0].sealed.data)).slice(0, 4)).not.toEqual([0xff, 0xd8, 0xff, 1]);
  });
});

describe('sync', () => {
  it('sends accepted events and empties the queue', async () => {
    await enqueue(event('delivery.transition', { target_status: 'accepted' }));
    await enqueue(event('delivery.transition', { target_status: 'en_route' }));
    const { client, sync } = fakeClient(acceptAll);
    const result = await syncOnce(client);
    expect(result).toMatchObject({ outcome: 'ok', accepted: 2, remaining: 0 });
    expect(sync).toHaveBeenCalledTimes(1);
    expect(sync.mock.calls[0][0].map((e) => e.payload.target_status)).toEqual(['accepted', 'en_route']);
  });

  it('treats duplicates as done (a retry after a lost response is harmless)', async () => {
    await enqueue(event('delivery.transition', { target_status: 'accepted' }));
    const { client } = fakeClient((events) => ({ duplicate: events.map((e) => e.event_id) }));
    expect(await syncOnce(client)).toMatchObject({ duplicates: 1, remaining: 0 });
  });

  it('keeps and flags rejected events without blocking later ones', async () => {
    const bad = event('delivery.transition', { target_status: 'delivered' });
    const good = event('delivery.transition', { target_status: 'accepted' });
    await enqueue(bad);
    await enqueue(good);
    const { client } = fakeClient((events) => ({ rejected: [bad.event_id], accepted: events.filter((e) => e.event_id !== bad.event_id).map((e) => e.event_id) }));
    const result = await syncOnce(client);
    expect(result).toMatchObject({ accepted: 1, rejected: 1, remaining: 0 });
    const left = await readQueue();
    expect(left).toHaveLength(1);
    expect(left[0].item.rejected).toBe(true);
    expect(await queueSize()).toBe(0); // flagged items do not count as pending
    const { client: again, sync } = fakeClient(acceptAll);
    await syncOnce(again);
    expect(sync).not.toHaveBeenCalled(); // and are not resent
  });

  it('stays queued when offline and recovers later', async () => {
    await enqueue(event('delivery.transition', { target_status: 'accepted' }));
    const offline = fakeClient(() => new TypeError('Failed to fetch'));
    expect(await syncOnce(offline.client)).toMatchObject({ outcome: 'offline', remaining: 1 });
    const online = fakeClient(acceptAll);
    expect(await syncOnce(online.client)).toMatchObject({ outcome: 'ok', accepted: 1, remaining: 0 });
  });

  it('maps auth failures and throttling', async () => {
    await enqueue(event('delivery.transition', { target_status: 'accepted' }));
    expect((await syncOnce(fakeClient(() => new DriverApiError(401, 'expired')).client)).outcome).toBe('auth');
    expect((await syncOnce(fakeClient(() => new DriverApiError(403, 'offline driver')).client)).outcome).toBe('auth');
    expect(await syncOnce(fakeClient(() => new DriverApiError(429, 'slow down', 17)).client)).toMatchObject({ outcome: 'throttled', retryAfter: 17, remaining: 1 });
    expect((await syncOnce(fakeClient(() => new DriverApiError(503, 'down')).client)).outcome).toBe('offline');
  });

  it('uploads the photo before the proof event and orders earlier events first', async () => {
    await enqueue(event('delivery.transition', { target_status: 'arrived' }));
    await enqueue(event('delivery.proof', { otp_code: '123456', recipient_name: 'Ada' }), new Blob([new Uint8Array([1, 2, 3])], { type: 'image/jpeg' }));
    await enqueue(event('delivery.payment', { collected_amount: '4000.00', method: 'cod' }));
    const order: string[] = [];
    const { client, sync, putUpload } = fakeClient(acceptAll);
    sync.mockImplementation(async (events: SyncEvent[]) => { order.push(`sync:${events.map((e) => e.event_type).join(',')}`); return { accepted_event_ids: events.map((e) => e.event_id), duplicate_event_ids: [], rejected_event_ids: [] }; });
    putUpload.mockImplementation(async () => { order.push('upload'); });
    expect(await syncOnce(client)).toMatchObject({ outcome: 'ok', accepted: 3, remaining: 0 });
    expect(order).toEqual(['sync:delivery.transition', 'upload', 'sync:delivery.proof,delivery.payment']);
    const proof = sync.mock.calls[1][0][0];
    expect(proof.payload).toMatchObject({ photo_url: 'media://t/j/photo-1.jpg', otp_code: '123456' });
    expect((await allRecords('blobs')).length).toBe(0); // photo bytes are deleted once sent
  });

  it('does not re-upload a photo after a failure that happens after the upload', async () => {
    await enqueue(event('delivery.proof', { recipient_name: 'Ada' }), new Blob([new Uint8Array([9])], { type: 'image/jpeg' }));
    const first = fakeClient(() => new TypeError('network dropped after upload'));
    expect((await syncOnce(first.client)).outcome).toBe('offline');
    expect(first.putUpload).toHaveBeenCalledTimes(1);
    const second = fakeClient(acceptAll);
    await syncOnce(second.client);
    expect(second.sync.mock.calls[0][0][0].payload.photo_url).toBe('media://t/j/photo-1.jpg');
  });

  it('batches large queues', async () => {
    for (let i = 0; i < 120; i++) await enqueue(event('delivery.transition', { n: i }));
    const { client, sync } = fakeClient(acceptAll);
    expect(await syncOnce(client)).toMatchObject({ accepted: 120, remaining: 0 });
    expect(sync.mock.calls.map((c) => c[0].length)).toEqual([50, 50, 20]);
  });
});

describe('helpers', () => {
  it('parses driver tokens without trusting them and rejects junk', () => {
    const payload = btoa(JSON.stringify({ sub: DRIVER, tid: 'tenant-1', typ: 'driver', exp: 2000000000 })).replace(/=/g, '');
    expect(parseDriverToken(`h.${payload}.s`)).toEqual({ driverId: DRIVER, tenantId: 'tenant-1', expiresAt: 2000000000 * 1000 });
    expect(parseDriverToken('not-a-token')).toBeNull();
    expect(parseDriverToken(`h.${btoa(JSON.stringify({ sub: 'x', tid: 'y', typ: 'user', exp: 1 }))}.s`)).toBeNull();
  });

  it('backs off exponentially, capped, and honours Retry-After', () => {
    expect(backoffMs(0)).toBe(2000);
    expect(backoffMs(3)).toBe(16000);
    expect(backoffMs(20)).toBe(5 * 60_000); // capped at five minutes
    expect(backoffMs(2, 30)).toBe(30000);
  });
});
