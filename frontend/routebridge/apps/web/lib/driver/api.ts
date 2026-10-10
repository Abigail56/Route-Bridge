import { API_BASE_URL } from '../api';
import type { SyncEvent } from './queue';

export type DriverSession = { token: string; tenantId: string; driverId: string };

export type DriverJob = {
  job_id: string; reference: string | null; status: string; customer_name: string | null; customer_phone_masked: string | null;
  address: string | null; landmark: string | null; plus_code: string | null; latitude: number | null; longitude: number | null;
  cod_amount: string | null; location_score: number | null; recipient_available: boolean | null;
  window_start: string | null; window_end: string | null;
  code_required?: boolean;
  merchant?: { name: string; phone: string | null; contact_person: string | null; address: string | null } | null;
};

export type SyncResponse = { accepted_event_ids: string[]; duplicate_event_ids: string[]; rejected_event_ids: string[] };
export type UploadGrant = { upload_url: string; method: 'PUT'; headers: Record<string, string>; object_url: string; max_bytes: number; needs_auth: boolean };

export class DriverApiError extends Error {
  status: number;
  retryAfter?: number;
  constructor(status: number, message: string, retryAfter?: number) {
    super(message);
    this.name = 'DriverApiError';
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

/** Reads the driver id / tenant / expiry from the token WITHOUT verifying it (the server verifies on every call). */
export function parseDriverToken(token: string): { driverId: string; tenantId: string; expiresAt: number } | null {
  try {
    const part = token.split('.')[1];
    const json = JSON.parse(atob(part.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(part.length / 4) * 4, '=')));
    if (json.typ !== 'driver' || !json.sub || !json.tid) return null;
    return { driverId: String(json.sub), tenantId: String(json.tid), expiresAt: Number(json.exp) * 1000 };
  } catch {
    return null;
  }
}

export function createDriverClient(session: DriverSession, fetchImpl: typeof fetch = (...args) => fetch(...args)) {
  const base = `${API_BASE_URL}/api/v1/driver/tenants/${session.tenantId}`;
  const auth = { Authorization: `Bearer ${session.token}` };

  async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetchImpl(`${base}${path}`, { ...init, headers: { 'Content-Type': 'application/json', ...auth, ...(init.headers || {}) } });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      const detail = typeof body?.detail === 'string' ? body.detail : `Request failed (${response.status})`;
      throw new DriverApiError(response.status, detail, Number(response.headers.get('Retry-After')) || undefined);
    }
    return response.json();
  }

  return {
    jobs: () => call<DriverJob[]>('/jobs'),
    sync: (events: SyncEvent[]) => call<SyncResponse>('/sync', { method: 'POST', body: JSON.stringify({ events }) }),
    requestOtp: (jobId: string) => call<{ expires_in_minutes: number; sent: boolean; relay?: boolean }>(`/jobs/${jobId}/otp`, { method: 'POST' }),
    pushKey: () => call<{ public_key: string | null }>('/push/key'),
    pushSubscribe: (subscription: { endpoint: string; keys: { p256dh: string; auth: string } }) => call<{ subscribed: boolean }>('/push/subscribe', { method: 'POST', body: JSON.stringify(subscription) }),
    pushUnsubscribe: (endpoint: string) => call<{ subscribed: boolean }>('/push/unsubscribe', { method: 'POST', body: JSON.stringify({ endpoint }) }),
    /** Only once arrived. `dial_number` is present when the phone's own dialer should place the call; otherwise the server bridges it. */
    callCustomer: (jobId: string) => call<{ status: string; dial_number?: string }>(`/jobs/${jobId}/call`, { method: 'POST' }),
    requestUpload: (jobId: string, contentType: string, kind: 'photo' | 'signature' = 'photo') =>
      call<UploadGrant>(`/jobs/${jobId}/uploads`, { method: 'POST', body: JSON.stringify({ kind, content_type: contentType }) }),
    /** Uploads the image to the granted URL (S3 presigned URLs must NOT carry our Authorization header). */
    async putUpload(grant: UploadGrant, blob: Blob): Promise<void> {
      const headers: Record<string, string> = { ...grant.headers, ...(grant.needs_auth ? auth : {}) };
      const response = await fetchImpl(grant.upload_url, { method: 'PUT', headers, body: blob });
      if (!response.ok) throw new DriverApiError(response.status, `Upload failed (${response.status})`);
    },
  };
}

export type DriverClient = ReturnType<typeof createDriverClient>;
