/**
 * Encrypted on-device storage for the driver app.
 *
 * Everything sensitive (the access token, queued events, cached jobs, photos waiting to upload) is encrypted with an
 * AES-GCM key that is generated on the device and stored as a NON-EXTRACTABLE CryptoKey in IndexedDB, so the raw key
 * material cannot be read back by scripts, and a copied database is unreadable without that key object.
 */

const DB_NAME = 'routebridge-driver';
const DB_VERSION = 1;

type StoreName = 'kv' | 'queue' | 'blobs';

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains('kv')) db.createObjectStore('kv');
      if (!db.objectStoreNames.contains('queue')) db.createObjectStore('queue', { keyPath: 'seq', autoIncrement: true });
      if (!db.objectStoreNames.contains('blobs')) db.createObjectStore('blobs', { keyPath: 'id' });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function run<T>(store: StoreName, mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T> | void): Promise<T | undefined> {
  const db = await openDb();
  try {
    return await new Promise<T | undefined>((resolve, reject) => {
      const tx = db.transaction(store, mode);
      const request = fn(tx.objectStore(store));
      tx.oncomplete = () => resolve(request ? (request.result as T) : undefined);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error);
    });
  } finally {
    db.close();
  }
}

export const kvGet = <T>(key: string) => run<T>('kv', 'readonly', (s) => s.get(key) as IDBRequest<T>);
export const kvSet = (key: string, value: unknown) => run('kv', 'readwrite', (s) => { s.put(value, key); }).then(() => undefined);
export const kvDelete = (key: string) => run('kv', 'readwrite', (s) => { s.delete(key); }).then(() => undefined);

async function deviceKey(): Promise<CryptoKey> {
  const existing = await kvGet<CryptoKey>('device-key');
  if (existing) return existing;
  const key = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
  await kvSet('device-key', key);
  return key;
}

export type Sealed = { iv: Uint8Array; data: ArrayBuffer };

export async function seal(bytes: Uint8Array): Promise<Sealed> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const data = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, await deviceKey(), bytes as BufferSource);
  return { iv, data };
}

export async function unseal(sealed: Sealed): Promise<Uint8Array> {
  return new Uint8Array(await crypto.subtle.decrypt({ name: 'AES-GCM', iv: sealed.iv as BufferSource }, await deviceKey(), sealed.data));
}

const encoder = new TextEncoder();
const decoder = new TextDecoder();
export const sealJson = (value: unknown) => seal(encoder.encode(JSON.stringify(value)));
export const unsealJson = async <T>(sealed: Sealed): Promise<T> => JSON.parse(decoder.decode(await unseal(sealed))) as T;

/** Encrypted key/value convenience (token, tenant id, cached jobs). */
export async function secureSet(key: string, value: unknown): Promise<void> {
  await kvSet(`sealed:${key}`, await sealJson(value));
}
export async function secureGet<T>(key: string): Promise<T | undefined> {
  const sealed = await kvGet<Sealed>(`sealed:${key}`);
  if (!sealed) return undefined;
  try { return await unsealJson<T>(sealed); } catch { return undefined; } // key lost/rotated: treat as empty
}
export const secureDelete = (key: string) => kvDelete(`sealed:${key}`);

export async function putSealed(store: 'queue' | 'blobs', record: Record<string, unknown>): Promise<void> {
  await run(store, 'readwrite', (s) => { s.put(record); });
}
export async function allRecords<T>(store: 'queue' | 'blobs'): Promise<T[]> {
  return ((await run(store, 'readonly', (s) => s.getAll())) ?? []) as T[];
}
export async function deleteRecord(store: 'queue' | 'blobs', key: IDBValidKey): Promise<void> {
  await run(store, 'readwrite', (s) => { s.delete(key); });
}
export async function getRecord<T>(store: 'queue' | 'blobs', key: IDBValidKey): Promise<T | undefined> {
  return (await run(store, 'readonly', (s) => s.get(key))) as T | undefined;
}
export async function clearAll(): Promise<void> {
  for (const store of ['kv', 'queue', 'blobs'] as const) await run(store, 'readwrite', (s) => { s.clear(); });
}
