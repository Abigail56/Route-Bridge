import { DriverApiError, type DriverClient } from './api';
import { loadPhoto, readQueue, removeItem, updateItem, type QueueItem, type SyncEvent } from './queue';

export type SyncOutcome = 'ok' | 'offline' | 'auth' | 'throttled';
export type SyncResult = { outcome: SyncOutcome; accepted: number; duplicates: number; rejected: number; remaining: number; retryAfter?: number };

const BATCH = 50;

/**
 * Flush the offline queue to the server, oldest first.
 * - Safe to call repeatedly or concurrently-after-failure: every event carries a stable event_id, so a retry after a
 *   lost response is reported as a duplicate by the server instead of being applied twice.
 * - Photos are uploaded just before the event that references them, so the proof event only ever points at an image
 *   that exists on the server.
 * - A rejected event (e.g. an invalid state change) is kept and flagged for the driver instead of blocking the queue.
 */
export async function syncOnce(client: DriverClient): Promise<SyncResult> {
  const result: SyncResult = { outcome: 'ok', accepted: 0, duplicates: 0, rejected: 0, remaining: 0 };
  const pending = (await readQueue()).filter((entry) => !entry.item.rejected);
  let batch: { seq: number; item: QueueItem }[] = [];

  async function flush(): Promise<boolean> {
    if (batch.length === 0) return true;
    const events: SyncEvent[] = batch.map((entry) => entry.item.event);
    const response = await client.sync(events);
    for (const entry of batch) {
      const id = entry.item.event.event_id;
      if (response.accepted_event_ids.includes(id)) { result.accepted++; await removeItem(entry.seq, entry.item.photoId); }
      else if (response.duplicate_event_ids.includes(id)) { result.duplicates++; await removeItem(entry.seq, entry.item.photoId); }
      else if (response.rejected_event_ids.includes(id)) { result.rejected++; await updateItem(entry.seq, { ...entry.item, rejected: true }); }
    }
    batch = [];
    return true;
  }

  try {
    for (const entry of pending) {
      if (entry.item.photoId) {
        await flush(); // keep ordering: everything before the proof goes first
        const photo = await loadPhoto(entry.item.photoId);
        if (!photo) {
          entry.item = { ...entry.item, photoId: undefined }; // image lost: send the proof without it rather than stall
        } else {
          const grant = await client.requestUpload(entry.item.event.aggregate_id, photo.type || 'image/jpeg');
          await client.putUpload(grant, photo);
          entry.item = { ...entry.item, event: { ...entry.item.event, payload: { ...entry.item.event.payload, photo_url: grant.object_url } } };
          await updateItem(entry.seq, entry.item); // remember the uploaded url so a crash here does not re-upload
        }
      }
      batch.push(entry);
      if (batch.length >= BATCH) await flush();
    }
    await flush();
  } catch (error) {
    if (error instanceof DriverApiError) {
      if (error.status === 401 || error.status === 403) result.outcome = 'auth';
      else if (error.status === 429) { result.outcome = 'throttled'; result.retryAfter = error.retryAfter; }
      else result.outcome = 'offline'; // 5xx and the like: retry later
    } else {
      result.outcome = 'offline'; // network failure
    }
  }
  result.remaining = (await readQueue()).filter((entry) => !entry.item.rejected).length;
  return result;
}

/** Delay before the next automatic attempt after consecutive failures (capped exponential backoff). */
export function backoffMs(failures: number, retryAfterSeconds?: number): number {
  if (retryAfterSeconds) return retryAfterSeconds * 1000;
  return Math.min(5 * 60_000, 2_000 * 2 ** Math.min(failures, 8));
}
