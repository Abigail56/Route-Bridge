import { allRecords, deleteRecord, getRecord, putSealed, seal, sealJson, unseal, unsealJson, type Sealed } from './store';

/** An event exactly as the backend's mobile-sync expects it. */
export type SyncEvent = {
  event_id: string;
  device_id: string;
  event_type: 'delivery.transition' | 'delivery.proof' | 'delivery.payment' | 'location.correction' | 'driver.location';
  aggregate_type: 'delivery_job' | 'driver';
  aggregate_id: string;
  payload: Record<string, unknown>;
  occurred_at: string;
};

/** Queue item: the event plus local bookkeeping. A photo is stored separately (encrypted) and uploaded at sync time. */
export type QueueItem = { event: SyncEvent; photoId?: string; attempts: number; rejected?: boolean };
type Row = { seq?: number; sealed: Sealed };

export async function enqueue(event: SyncEvent, photo?: Blob): Promise<void> {
  let photoId: string | undefined;
  if (photo) {
    photoId = crypto.randomUUID();
    const bytes = new Uint8Array(await photo.arrayBuffer());
    await putSealed('blobs', { id: photoId, type: photo.type || 'image/jpeg', sealed: await seal(bytes) });
  }
  await putSealed('queue', { sealed: await sealJson({ event, photoId, attempts: 0 } satisfies QueueItem) });
}

/** Queue contents in insertion order (the order events happened in, which the server's state machine requires). */
export async function readQueue(): Promise<{ seq: number; item: QueueItem }[]> {
  const rows = (await allRecords<Row>('queue')).sort((a, b) => (a.seq ?? 0) - (b.seq ?? 0));
  const items: { seq: number; item: QueueItem }[] = [];
  for (const row of rows) {
    try { items.push({ seq: row.seq as number, item: await unsealJson<QueueItem>(row.sealed) }); }
    catch { await deleteRecord('queue', row.seq as number); } // undecryptable (key lost): drop rather than block the queue
  }
  return items;
}

export async function updateItem(seq: number, item: QueueItem): Promise<void> {
  await putSealed('queue', { seq, sealed: await sealJson(item) });
}

export async function removeItem(seq: number, photoId?: string): Promise<void> {
  await deleteRecord('queue', seq);
  if (photoId) await deleteRecord('blobs', photoId);
}

export async function loadPhoto(photoId: string): Promise<Blob | undefined> {
  const record = await getRecord<{ id: string; type: string; sealed: Sealed }>('blobs', photoId);
  if (!record) return undefined;
  return new Blob([(await unseal(record.sealed)) as BlobPart], { type: record.type });
}

/** Only the newest GPS ping is worth sending: replace any older unsent one instead of queueing a trail. */
export async function enqueueLocation(event: SyncEvent): Promise<void> {
  for (const { seq, item } of await readQueue()) {
    if (item.event.event_type === 'driver.location' && !item.rejected) await removeItem(seq);
  }
  await enqueue(event);
}

export async function queueSize(): Promise<number> {
  return (await readQueue()).filter((entry) => !entry.item.rejected).length;
}
