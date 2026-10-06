export type OrderRead = {
  id: string;
  tenant_id: string;
  merchant_id: string;
  customer_id: string;
  external_ref: string;
  status: string;
  currency: string;
  // Decimals are serialized by the API as strings to keep precision.
  total_amount: string | number;
  cod_amount: string | number;
  delivery_job_id: string | null;
  stop_id: string | null;
  stop_status: string | null;
  created_at: string;
  customer_name: string | null;
  merchant_name: string | null;
  address_text: string | null;
  landmark: string | null;
  location_confidence: string | null;
  job_status: string | null;
  driver_id: string | null;
  driver_name: string | null;
  location_corrected: boolean;
  location_score: number | null;
  latitude: number | null;
  longitude: number | null;
  plus_code: string | null;
  recipient_available: boolean | null;
  service_zone_id: string | null;
  window_start: string | null;
  window_end: string | null;
  tracking_token: string | null;
};

export type Zone = { id: string; code: string; name: string };
export type RateCard = { id: string; service_zone_id: string; name: string; base_amount: string | number; cod_fee: string | number; currency: string };
export type Member = { membership_id: string; user_id: string; clerk_user_id: string; email: string | null; full_name: string | null; role: string; status: string };
export type AuditRow = { id: string; event_type: string; aggregate_type: string; aggregate_id: string; actor_type: string; occurred_at: string; payload: Record<string, unknown> };
export type ExceptionItem = { kind: string; severity: 'high' | 'medium'; order_id: string | null; job_id: string | null; external_ref: string | null; detail: string; since: string };
export type Summary = {
  period_days: number; jobs_total: number; jobs_delivered: number; jobs_failed_or_returned: number;
  on_time_rate: number | null; on_time_sample: number; first_attempt_success_rate: number | null;
  failure_reasons: { service_zone_id: string | null; zone_name: string | null; reason_code: string; count: number }[];
  cod: { expected: string; collected: string; open_reconciliation_items: number; open_variance: string };
  cost_per_stop: string | null; stops_per_driver: number | null;
};
export type Batch = {
  service_zone_id: string | null; zone_name: string | null; window_start: string | null; window_end: string | null;
  jobs: { job_id: string; order_id: string; external_ref: string | null; address_text: string | null; location_score: number | null }[];
  suggested_sequence: string[];
};
export type StatementResult = { matched: number; mismatched: number; unmatched: { row: number; reference: string; amount: string }[]; invalid_rows: { row: number; reason: string }[] };

export type MyTenant = { tenant_id: string; name: string; role: string };
export type Company = { tenant_id: string; name: string; status: string; created_at: string; owners: string[]; members: number; drivers: number; orders: number };
export type PersonWorkspace = { tenant_id: string; tenant_name: string; role: string; status: string };
export type Person = { clerk_user_id: string; email: string | null; full_name: string | null; status: string; is_platform_admin: boolean; workspaces: PersonWorkspace[] };
export type PlatformAdminRow = { clerk_user_id: string; email: string | null; full_name: string | null; source: 'database' | 'settings'; added_by: string | null; created_at: string | null };
export type HealthItem = { name: string; status: 'ok' | 'warning' | 'down' | 'off'; detail: string };
export type SystemHealth = { checked_at: string; items: HealthItem[]; totals: Record<string, number> };
export type PlatformAuditRow = { occurred_at: string; scope: 'platform' | 'workspace'; actor: string; action: string; target: string; detail: string };
export type PlatformApi = {
  companies: () => Promise<Company[]>;
  setCompanyStatus: (tenantId: string, status: 'active' | 'suspended') => Promise<Company>;
  assignOwner: (tenantId: string, input: { clerk_user_id: string; email?: string; full_name?: string; replace_existing: boolean }) => Promise<Company>;
  people: (q: string) => Promise<Person[]>;
  setPersonStatus: (clerkUserId: string, status: 'active' | 'inactive') => Promise<Person>;
  addPerson: (tenantId: string, input: { clerk_user_id: string; role: string; email?: string; full_name?: string }) => Promise<Person>;
  admins: () => Promise<PlatformAdminRow[]>;
  addAdmin: (input: { clerk_user_id: string; email?: string; full_name?: string }) => Promise<PlatformAdminRow[]>;
  removeAdmin: (clerkUserId: string) => Promise<PlatformAdminRow[]>;
  health: () => Promise<SystemHealth>;
  audit: () => Promise<PlatformAuditRow[]>;
};

export type Profile = { subject: string | null; email: string | null; name: string | null; is_platform_admin: boolean; tenants: MyTenant[] };
export type OperatingArea = { id: string; code: string; name: string };
export type ReconciliationItem = { id: string; payment_id: string; status: string; variance_amount: string | number; resolution_note: string | null; created_at: string };

export type Merchant = { id: string; name: string };
export type Driver = { id: string; name: string; phone: string; fleet_type: string; status: string };
export type OrderInput = {
  merchant_id: string; customer_name: string; customer_phone: string; external_ref: string;
  total_amount: string; cod_amount: string; address_text: string; landmark?: string; delivery_notes?: string;
  location_confidence: 'unverified' | 'geocoded' | 'customer_confirmed' | 'driver_confirmed';
  plus_code?: string; recipient_available?: boolean; service_zone_id?: string; window_start?: string; window_end?: string;
};

export type ApiClient = {
  getProfile: () => Promise<Profile>;
  createTenant: (name: string) => Promise<{ id: string; name: string }>;
  getOperatingAreas: () => Promise<OperatingArea[]>;
  createMerchant: (tenantId: string, name: string) => Promise<Merchant>;
  createZone: (tenantId: string, input: { operating_area_id: string; code: string; name: string }) => Promise<Zone>;
  getZones: (tenantId: string) => Promise<Zone[]>;
  getRateCards: (tenantId: string) => Promise<RateCard[]>;
  createRateCard: (tenantId: string, input: { service_zone_id: string; name: string; base_amount: string }) => Promise<RateCard>;
  getSummary: (tenantId: string, days?: number) => Promise<Summary>;
  getExceptions: (tenantId: string) => Promise<ExceptionItem[]>;
  getMembers: (tenantId: string) => Promise<Member[]>;
  addMember: (tenantId: string, input: { clerk_user_id: string; role: string; email?: string; full_name?: string }) => Promise<Member>;
  updateMember: (tenantId: string, membershipId: string, input: { role?: string; status?: 'active' | 'inactive' }) => Promise<Member>;
  getAudit: (tenantId: string, limit?: number) => Promise<AuditRow[]>;
  getBatches: (tenantId: string) => Promise<Batch[]>;
  assignBatch: (tenantId: string, jobIds: string[], driverId: string) => Promise<{ assigned: string[]; failed: { job_id: string; reason: string }[] }>;
  updateDriver: (tenantId: string, driverId: string, input: { status?: 'available' | 'offline' }) => Promise<Driver>;
  correctLocation: (tenantId: string, jobId: string, input: Record<string, unknown>) => Promise<void>;
  reissueTrackingLink: (tenantId: string, jobId: string) => Promise<{ tracking_token: string }>;
  importStatement: (tenantId: string, file: File) => Promise<StatementResult>;
  downloadPayouts: (tenantId: string, from: string, to: string) => Promise<Blob>;
  getMerchants: (tenantId: string) => Promise<Merchant[]>;
  getDrivers: (tenantId: string) => Promise<Driver[]>;
  createDriver: (tenantId: string, input: { name: string; phone: string; fleet_type: string }) => Promise<Driver>;
  createOrder: (tenantId: string, input: OrderInput, idempotencyKey: string) => Promise<OrderRead>;
  assignDriver: (tenantId: string, jobId: string, driverId: string) => Promise<void>;
  transitionJob: (tenantId: string, jobId: string, targetStatus: string, reasonCode?: string) => Promise<void>;
  resolveReconciliation: (tenantId: string, itemId: string, note: string) => Promise<void>;
  getOrders: (tenantId: string) => Promise<OrderRead[]>;
  getMyTenants: () => Promise<MyTenant[]>;
  getReconciliation: (tenantId: string) => Promise<ReconciliationItem[]>;
  authAttempt: (mode: 'signin' | 'signup', identifier: string) => Promise<void>;
  platform: PlatformApi;
};

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export class ApiError extends Error {
  status: number;
  retryAfter?: number;
  constructor(status: number, message: string, retryAfter?: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

/** FastAPI returns `detail` as a string, or as a list of validation errors for 422. */
export function formatDetail(detail: unknown, status: number): string {
  if (typeof detail === 'string' && detail) return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((item) => {
        if (typeof item === 'string') return item;
        const loc = Array.isArray(item?.loc) ? item.loc.filter((part: unknown) => part !== 'body').join('.') : '';
        return [loc, item?.msg].filter(Boolean).join(': ') || 'Invalid value';
      })
      .join('; ');
  }
  return `RouteBridge API error ${status}`;
}

export function friendlyMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return 'Your session has expired. Please sign in again.';
    if (error.status === 403) return 'Your account does not have access to this workspace yet. Ask an admin to add you.';
    if (error.status === 429) return error.retryAfter ? `Too many attempts. Try again in ${error.retryAfter} seconds.` : 'Too many attempts. Please try again later.';
    if (error.status === 503) return 'The service is temporarily unavailable. Please try again shortly.';
    return error.message;
  }
  return error instanceof Error ? error.message : 'Something went wrong';
}

export async function readError(response: Response): Promise<ApiError> {
  const body = await response.json().catch(() => ({}));
  const retryAfter = Number(response.headers.get('Retry-After')) || undefined;
  return new ApiError(response.status, formatDetail(body?.detail, response.status), retryAfter);
}

export function createApiClient(getToken: () => Promise<string | null>): ApiClient {
  async function request<T>(path: string, init: RequestInit = {}, retried = false): Promise<T> {
    const token = await getToken();
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(init.headers || {}) },
    });
    // A 401 means the request was rejected before it did anything, so one retry with a fresh token is always safe
    // (covers a token that expired between being issued and being checked).
    if (response.status === 401 && !retried) {
      await new Promise((resolve) => setTimeout(resolve, 600));
      return request<T>(path, init, true);
    }
    if (!response.ok) throw await readError(response);
    return response.json();
  }
  async function upload<T>(path: string, form: FormData): Promise<T> {
    const token = await getToken();
    const response = await fetch(`${API_BASE_URL}${path}`, { method: 'POST', body: form, headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (!response.ok) throw await readError(response);
    return response.json();
  }
  async function download(path: string): Promise<Blob> {
    const token = await getToken();
    const response = await fetch(`${API_BASE_URL}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (!response.ok) throw await readError(response);
    return response.blob();
  }
  const patch = (path: string, body: unknown) => request<any>(path, { method: 'PATCH', body: JSON.stringify(body) });
  const post = (path: string, body: unknown, headers: Record<string, string> = {}) => request<any>(path, { method: 'POST', body: JSON.stringify(body), headers });
  return {
    getProfile: () => request('/api/v1/auth/me/profile'),
    createTenant: (name) => post('/api/v1/admin/tenants', { name }),
    getOperatingAreas: () => request('/api/v1/admin/operating-areas'),
    createMerchant: (t, name) => post(`/api/v1/admin/tenants/${t}/merchants`, { name }),
    createZone: (t, input) => post(`/api/v1/admin/tenants/${t}/zones`, input),
    getZones: (t) => request(`/api/v1/tenants/${t}/zones`),
    getRateCards: (t) => request(`/api/v1/tenants/${t}/rate-cards`),
    createRateCard: (t, input) => post(`/api/v1/tenants/${t}/rate-cards`, input),
    getSummary: (t, days = 30) => request(`/api/v1/tenants/${t}/reports/summary?days=${days}`),
    getExceptions: (t) => request(`/api/v1/tenants/${t}/exceptions`),
    getMembers: (t) => request(`/api/v1/tenants/${t}/members`),
    addMember: (t, input) => post(`/api/v1/tenants/${t}/members`, input),
    updateMember: (t, id, input) => patch(`/api/v1/tenants/${t}/members/${id}`, input),
    getAudit: (t, limit = 100) => request(`/api/v1/tenants/${t}/audit?limit=${limit}`),
    getBatches: (t) => request(`/api/v1/tenants/${t}/dispatch/batches`),
    assignBatch: (t, jobIds, driverId) => post(`/api/v1/tenants/${t}/dispatch/batches/assign`, { job_ids: jobIds, driver_id: driverId }),
    updateDriver: (t, id, input) => patch(`/api/v1/tenants/${t}/drivers/${id}`, input),
    correctLocation: (t, jobId, input) => post(`/api/v1/tenants/${t}/delivery-jobs/${jobId}/location-corrections`, input).then(() => undefined),
    reissueTrackingLink: (t, jobId) => post(`/api/v1/tenants/${t}/delivery-jobs/${jobId}/tracking-link/reissue`, {}),
    importStatement: (t, file) => { const form = new FormData(); form.append('file', file); return upload(`/api/v1/tenants/${t}/reconciliation/import-statement`, form); },
    downloadPayouts: (t, from, to) => download(`/api/v1/tenants/${t}/payouts/export?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`),
    getMerchants: (tenantId) => request(`/api/v1/tenants/${tenantId}/merchants`),
    getDrivers: (tenantId) => request(`/api/v1/tenants/${tenantId}/drivers`),
    createDriver: (tenantId, input) => post(`/api/v1/tenants/${tenantId}/drivers`, input),
    // The caller supplies one key per form submission so double-clicks and retries cannot create duplicates.
    createOrder: (tenantId, input, idempotencyKey) => post(`/api/v1/tenants/${tenantId}/orders`, input, { 'Idempotency-Key': idempotencyKey }),
    assignDriver: (tenantId, jobId, driverId) => post(`/api/v1/tenants/${tenantId}/delivery-jobs/${jobId}/assignments`, { driver_id: driverId }).then(() => undefined),
    transitionJob: (tenantId, jobId, targetStatus, reasonCode) => post(`/api/v1/tenants/${tenantId}/delivery-jobs/${jobId}/transitions`, { target_status: targetStatus, ...(reasonCode ? { reason_code: reasonCode } : {}) }).then(() => undefined),
    resolveReconciliation: (tenantId, itemId, note) => post(`/api/v1/tenants/${tenantId}/reconciliation/${itemId}/resolve`, { resolution_note: note }).then(() => undefined),
    getOrders: (tenantId) => request(`/api/v1/tenants/${tenantId}/orders?limit=200`),
    getMyTenants: () => request('/api/v1/auth/me/tenants'),
    getReconciliation: (tenantId) => request(`/api/v1/tenants/${tenantId}/reconciliation`),
    platform: {
      companies: () => request('/api/v1/platform/tenants'),
      setCompanyStatus: (tenantId, status) => post(`/api/v1/platform/tenants/${tenantId}/status`, { status }),
      assignOwner: (tenantId, input) => post(`/api/v1/platform/tenants/${tenantId}/owner`, input),
      people: (q) => request(`/api/v1/platform/users?q=${encodeURIComponent(q)}`),
      setPersonStatus: (clerkUserId, status) => post(`/api/v1/platform/users/${encodeURIComponent(clerkUserId)}/status`, { status }),
      addPerson: (tenantId, input) => post(`/api/v1/platform/tenants/${tenantId}/members`, input),
      admins: () => request('/api/v1/platform/admins'),
      addAdmin: (input) => post('/api/v1/platform/admins', input),
      removeAdmin: (clerkUserId) => request(`/api/v1/platform/admins/${encodeURIComponent(clerkUserId)}`, { method: 'DELETE' }),
      health: () => request('/api/v1/platform/health'),
      audit: () => request('/api/v1/platform/audit'),
    },
    authAttempt: (mode, identifier) => request(`/api/v1/auth/${mode}`, { method: 'POST', body: JSON.stringify({ identifier }) }).then(() => undefined),
  };
}
