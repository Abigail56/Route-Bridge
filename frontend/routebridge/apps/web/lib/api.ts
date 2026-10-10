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
  code_verified?: boolean;
};

export type BillingPlan = { key: string; name: string; price_ngn: number; riders: number | null; staff: number | null; merchants: number | null; orders_per_month: number | null; blurb: string };
export type Billing = { plan: BillingPlan; status: 'active' | 'ending' | 'grace' | 'expired'; valid_until: string | null; days_left: number | null; enforced: boolean; payments_enabled: boolean; usage: { riders: number; staff: number; merchants: number; orders: number }; plans: BillingPlan[] };

export type StatementLine = { order_ref: string; delivered_at: string; customer: string; cod_due: string; cash_collected: string; delivery_fee: string; note: string };
export type Statement = { merchant_id: string; merchant_name: string; currency: string; deliveries: number; cash_collected: string; delivery_fees: string; net_payable: string; lines: StatementLine[] };

export type Claim = { id: string; merchant_id: string; merchant_name: string | null; order_id: string | null; order_ref: string | null; kind: string; status: string; raised_by: string; description: string; amount_claimed: string; amount_approved: string | null; resolution_note: string | null; created_at: string; updated_at: string; decided_at: string | null };

export type DeliveryCodeRequest = { id: string; job_id: string; order_ref: string | null; customer_name: string | null; customer_phone: string | null; driver_name: string | null; code: string; message: string; requested_at: string; expires_at: string; minutes_left: number };

export type Zone = { id: string; code: string; name: string };
export type RateCard = { id: string; service_zone_id: string; name: string; base_amount: string | number; cod_fee: string | number; currency: string };
export type Member = { membership_id: string; user_id: string; clerk_user_id: string; email: string | null; full_name: string | null; role: string; status: string; merchant_id?: string | null; merchant_name?: string | null };
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

export type MyTenant = { tenant_id: string; name: string; role: string; merchant_id?: string | null; merchant_name?: string | null };

export type PortalMe = { merchant_id: string; merchant_name: string; workspace_name: string; contact_phone: string | null; contact_email: string | null; profile_complete?: boolean };
export type MerchantProfile = { merchant_id: string; merchant_name: string; contact_phone: string | null; contact_email: string | null; contact_person: string | null; address_line: string | null; landmark: string | null; city: string | null; state: string | null; bank_name: string | null; account_number: string | null; account_name: string | null; complete: boolean; bank_visible: boolean; updated_at: string | null };
export type ProfileInput = { contact_phone: string; contact_email?: string; contact_person?: string; address_line: string; landmark?: string; city: string; state: string; bank_name: string; account_number: string; account_name: string };
export type PortalOrder = { id: string; external_ref: string; status: string; customer_name: string | null; address_text: string | null; landmark: string | null; total_amount: string; cod_amount: string; currency: string; created_at: string; tracking_token: string | null; rider_assigned: boolean; code_verified?: boolean };
export type PortalSummary = { orders_total: number; in_progress: number; delivered: number; problems: number; cod_to_collect: string; cod_collected: string };
export type PortalOrderInput = { customer_name: string; customer_phone: string; address_text: string; external_ref?: string; landmark?: string; delivery_notes?: string; total_amount?: string; cod_amount?: string };
export type PortalApi = {
  me: (tenantId: string) => Promise<PortalMe>;
  profile: (tenantId: string) => Promise<MerchantProfile>;
  saveProfile: (tenantId: string, input: ProfileInput) => Promise<MerchantProfile>;
  setPhone: (tenantId: string, phone: string, email?: string) => Promise<PortalMe>;
  orders: (tenantId: string) => Promise<PortalOrder[]>;
  summary: (tenantId: string) => Promise<PortalSummary>;
  createOrder: (tenantId: string, input: PortalOrderInput, idempotencyKey: string) => Promise<PortalOrder>;
  statement: (tenantId: string, from: string, to: string) => Promise<Statement>;
  claims: (tenantId: string) => Promise<Claim[]>;
  openClaim: (tenantId: string, input: { kind: string; description: string; amount_claimed: string; order_id?: string }) => Promise<Claim>;
  downloadStatement: (tenantId: string, from: string, to: string) => Promise<Blob>;
};
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
  renameCompany: (tenantId: string, name: string) => Promise<Company>;
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

export type AutoAssignResult = { job_id: string; assigned: boolean; driver_id: string | null; driver_name: string | null; method: 'nearest' | 'next_available' | null; distance_m: number | null; reason: 'not_waiting' | 'no_available_driver' | 'no_driver_nearby' | null };
export type AutoAssignAll = { assigned: number; waiting: number; results: AutoAssignResult[] };

export type LiveDriver = {
  driver_id: string; name: string; phone: string; fleet_type: string; status: string;
  latitude: number | null; longitude: number | null; last_seen_seconds: number | null; stale: boolean;
  job: { job_id: string; order_ref: string | null; status: string; address_text: string | null; dropoff_latitude: number | null; dropoff_longitude: number | null; eta_minutes: number | null } | null;
};
export type LiveTracking = { drivers: LiveDriver[]; waiting: { job_id: string; order_ref: string | null; latitude: number; longitude: number }[] };

export type Profile = { subject: string | null; email: string | null; name: string | null; is_platform_admin: boolean; tenants: MyTenant[] };
export type OperatingArea = { id: string; code: string; name: string };
export type ReconciliationItem = { id: string; payment_id: string; status: string; variance_amount: string | number; resolution_note: string | null; created_at: string };

export type Merchant = { id: string; name: string; contact_phone?: string | null; contact_email?: string | null; notify_orders?: boolean };
export type Driver = { id: string; name: string; phone: string; fleet_type: string; status: string; photo?: string | null };
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
  createMerchant: (tenantId: string, name: string, clerkUserId: string, contactPhone?: string, contactEmail?: string) => Promise<Merchant>;
  updateMerchant: (tenantId: string, merchantId: string, input: { contact_phone?: string; contact_email?: string; notify_orders?: boolean }) => Promise<Merchant>;
  setDriverPhoto: (tenantId: string, driverId: string, dataUrl: string) => Promise<{ photo: string }>;
  removeDriverPhoto: (tenantId: string, driverId: string) => Promise<{ photo: null }>;
  createZone: (tenantId: string, input: { operating_area_id: string; code: string; name: string }) => Promise<Zone>;
  getZones: (tenantId: string) => Promise<Zone[]>;
  getRateCards: (tenantId: string) => Promise<RateCard[]>;
  createRateCard: (tenantId: string, input: { service_zone_id: string; name: string; base_amount: string }) => Promise<RateCard>;
  getSummary: (tenantId: string, days?: number) => Promise<Summary>;
  getExceptions: (tenantId: string) => Promise<ExceptionItem[]>;
  getMembers: (tenantId: string) => Promise<Member[]>;
  addMember: (tenantId: string, input: { clerk_user_id: string; role: string; email?: string; full_name?: string; merchant_id?: string }) => Promise<Member>;
  updateMember: (tenantId: string, membershipId: string, input: { role?: string; status?: 'active' | 'inactive' }) => Promise<Member>;
  getAudit: (tenantId: string, limit?: number) => Promise<AuditRow[]>;
  getBatches: (tenantId: string) => Promise<Batch[]>;
  assignBatch: (tenantId: string, jobIds: string[], driverId: string) => Promise<{ assigned: string[]; failed: { job_id: string; reason: string }[] }>;
  updateDriver: (tenantId: string, driverId: string, input: { status?: 'available' | 'offline' }) => Promise<Driver>;
  correctLocation: (tenantId: string, jobId: string, input: Record<string, unknown>) => Promise<void>;
  reissueTrackingLink: (tenantId: string, jobId: string) => Promise<{ tracking_token: string }>;
  importStatement: (tenantId: string, file: File) => Promise<StatementResult>;
  downloadPayouts: (tenantId: string, from: string, to: string) => Promise<Blob>;
  getStatement: (tenantId: string, merchantId: string, from: string, to: string) => Promise<Statement>;
  getClaims: (tenantId: string, status?: string) => Promise<Claim[]>;
  updateClaim: (tenantId: string, claimId: string, input: { status?: string; amount_approved?: string; resolution_note?: string; internal_note?: string }) => Promise<Claim>;
  downloadStatement: (tenantId: string, merchantId: string, from: string, to: string) => Promise<Blob>;
  getMerchants: (tenantId: string) => Promise<Merchant[]>;
  getMerchantProfiles: (tenantId: string) => Promise<MerchantProfile[]>;
  removeMerchant: (tenantId: string, merchantId: string) => Promise<{ removed: boolean; logins_switched_off: number }>;
  getRemovedMerchants: (tenantId: string) => Promise<Merchant[]>;
  restoreMerchant: (tenantId: string, merchantId: string) => Promise<{ restored: boolean; logins_switched_on: number }>;
  getDrivers: (tenantId: string) => Promise<Driver[]>;
  createDriver: (tenantId: string, input: { name: string; phone: string; fleet_type: string }) => Promise<Driver>;
  createOrder: (tenantId: string, input: OrderInput, idempotencyKey: string) => Promise<OrderRead>;
  assignDriver: (tenantId: string, jobId: string, driverId: string) => Promise<void>;
  autoAssignJob: (tenantId: string, jobId: string) => Promise<AutoAssignResult>;
  issueDriverToken: (tenantId: string, driverId: string) => Promise<{ access_token: string; token_type: string; expires_in: number }>;
  getLiveTracking: (tenantId: string) => Promise<LiveTracking>;
  autoAssignAll: (tenantId: string) => Promise<AutoAssignAll>;
  getDispatchSettings: (tenantId: string) => Promise<{ auto_assign: boolean }>;
  setDispatchSettings: (tenantId: string, autoAssign: boolean) => Promise<{ auto_assign: boolean }>;
  transitionJob: (tenantId: string, jobId: string, targetStatus: string, reasonCode?: string) => Promise<void>;
  resolveReconciliation: (tenantId: string, itemId: string, note: string) => Promise<void>;
  getOrders: (tenantId: string) => Promise<OrderRead[]>;
  getMyTenants: () => Promise<MyTenant[]>;
  getReconciliation: (tenantId: string) => Promise<ReconciliationItem[]>;
  authAttempt: (mode: 'signin' | 'signup', identifier: string) => Promise<void>;
  renameWorkspace: (tenantId: string, name: string) => Promise<{ id: string; name: string }>;
  getBilling: (tenantId: string) => Promise<Billing>;
  getDeliveryCodes: (tenantId: string) => Promise<DeliveryCodeRequest[]>;
  markDeliveryCodeSent: (tenantId: string, requestId: string) => Promise<{ sent: boolean }>;
  startCheckout: (tenantId: string, plan: string) => Promise<{ authorization_url: string; reference: string }>;
  verifyPayment: (tenantId: string, reference: string) => Promise<Billing>;
  platform: PlatformApi;
  portal: PortalApi;
};

/**
 * Still unauthorised after fresh-token retries: the session really is gone. Send the person to sign in again, once a minute at
 * most, so a misconfigured server can never trap them in a redirect loop (they just see the error instead).
 */
function recoverFromExpiredSession() {
  if (typeof window === 'undefined' || window.location.pathname.startsWith('/sign-')) return;
  try {
    const last = Number(window.sessionStorage.getItem('rb-session-redirect') ?? 0);
    if (Date.now() - last < 60_000) return;
    window.sessionStorage.setItem('rb-session-redirect', String(Date.now()));
  } catch { /* storage blocked: skip the redirect */ return; }
  window.location.assign(`/sign-in?redirect_url=${encodeURIComponent(window.location.pathname)}`);
}

// 'same-origin' = call the API on the address the page itself came from (the demo tunnel serves both from one address).
export const API_BASE_URL = apiBaseUrl(process.env.NEXT_PUBLIC_API_BASE_URL);

export function apiBaseUrl(configured: string | undefined): string {
  return configured === 'same-origin' ? '' : configured || 'http://localhost:8000';
}

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

export function createApiClient(getToken: (options?: { skipCache?: boolean }) => Promise<string | null>): ApiClient {
  async function request<T>(path: string, init: RequestInit = {}, retried = false, attempt = 1): Promise<T> {
    const token = await getToken(retried ? { skipCache: true } : undefined);
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(init.headers || {}) },
    });
    // A 401 means the request was rejected before it did anything, so one retry with a fresh token is always safe
    // (covers a token that expired between being issued and being checked).
    if (response.status === 401 && attempt < 3) {
      // Ask Clerk for a brand-new token (not the cached one) and try again, a little slower each time.
      await new Promise((resolve) => setTimeout(resolve, 400 * attempt));
      return request<T>(path, init, true, attempt + 1);
    }
    if (response.status === 401) recoverFromExpiredSession();
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
    createMerchant: (t, name, clerkUserId, contactPhone, contactEmail) => post(`/api/v1/admin/tenants/${t}/merchants`, { name, clerk_user_id: clerkUserId, ...(contactPhone ? { contact_phone: contactPhone } : {}), ...(contactEmail ? { contact_email: contactEmail } : {}) }),
    updateMerchant: (t, id, input) => patch(`/api/v1/admin/tenants/${t}/merchants/${id}`, input),
    setDriverPhoto: (t, id, dataUrl) => request(`/api/v1/tenants/${t}/drivers/${id}/photo`, { method: 'PUT', body: JSON.stringify({ data_url: dataUrl }) }),
    removeDriverPhoto: (t, id) => request(`/api/v1/tenants/${t}/drivers/${id}/photo`, { method: 'DELETE' }),
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
    getClaims: (t, status) => request(`/api/v1/tenants/${t}/claims${status ? `?status=${encodeURIComponent(status)}` : ''}`),
    updateClaim: (t, id, input) => patch(`/api/v1/tenants/${t}/claims/${id}`, input),
    getStatement: (t, m, from, to) => request(`/api/v1/tenants/${t}/merchants/${m}/statement?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`),
    downloadStatement: (t, m, from, to) => download(`/api/v1/tenants/${t}/merchants/${m}/statement.csv?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`),
    downloadPayouts: (t, from, to) => download(`/api/v1/tenants/${t}/payouts/export?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`),
    getMerchants: (tenantId) => request(`/api/v1/tenants/${tenantId}/merchants`),
    getMerchantProfiles: (tenantId) => request(`/api/v1/tenants/${tenantId}/merchant-profiles`),
    removeMerchant: (tenantId, merchantId) => request(`/api/v1/admin/tenants/${tenantId}/merchants/${merchantId}`, { method: 'DELETE' }),
    getRemovedMerchants: (tenantId) => request(`/api/v1/admin/tenants/${tenantId}/removed-merchants`),
    restoreMerchant: (tenantId, merchantId) => request(`/api/v1/admin/tenants/${tenantId}/merchants/${merchantId}/restore`, { method: 'POST' }),
    getDrivers: (tenantId) => request(`/api/v1/tenants/${tenantId}/drivers`),
    createDriver: (tenantId, input) => post(`/api/v1/tenants/${tenantId}/drivers`, input),
    // The caller supplies one key per form submission so double-clicks and retries cannot create duplicates.
    createOrder: (tenantId, input, idempotencyKey) => post(`/api/v1/tenants/${tenantId}/orders`, input, { 'Idempotency-Key': idempotencyKey }),
    getLiveTracking: (tenantId) => request(`/api/v1/tenants/${tenantId}/tracking/drivers`),
    issueDriverToken: (tenantId, driverId) => post(`/api/v1/tenants/${tenantId}/drivers/${driverId}/token`, {}),
    autoAssignJob: (tenantId, jobId) => post(`/api/v1/tenants/${tenantId}/delivery-jobs/${jobId}/auto-assign`, {}),
    autoAssignAll: (tenantId) => post(`/api/v1/tenants/${tenantId}/dispatch/auto-assign`, {}),
    getDispatchSettings: (tenantId) => request(`/api/v1/tenants/${tenantId}/dispatch/settings`),
    setDispatchSettings: (tenantId, autoAssign) => patch(`/api/v1/tenants/${tenantId}/dispatch/settings`, { auto_assign: autoAssign }),
    assignDriver: (tenantId, jobId, driverId) => post(`/api/v1/tenants/${tenantId}/delivery-jobs/${jobId}/assignments`, { driver_id: driverId }).then(() => undefined),
    transitionJob: (tenantId, jobId, targetStatus, reasonCode) => post(`/api/v1/tenants/${tenantId}/delivery-jobs/${jobId}/transitions`, { target_status: targetStatus, ...(reasonCode ? { reason_code: reasonCode } : {}) }).then(() => undefined),
    resolveReconciliation: (tenantId, itemId, note) => post(`/api/v1/tenants/${tenantId}/reconciliation/${itemId}/resolve`, { resolution_note: note }).then(() => undefined),
    getOrders: (tenantId) => request(`/api/v1/tenants/${tenantId}/orders?limit=200`),
    getMyTenants: () => request('/api/v1/auth/me/tenants'),
    getReconciliation: (tenantId) => request(`/api/v1/tenants/${tenantId}/reconciliation`),
    getBilling: (t) => request(`/api/v1/tenants/${t}/billing`),
    getDeliveryCodes: (t) => request(`/api/v1/tenants/${t}/delivery-codes`),
    markDeliveryCodeSent: (t, id) => post(`/api/v1/tenants/${t}/delivery-codes/${id}/sent`, {}),
    startCheckout: (t, plan) => post(`/api/v1/tenants/${t}/billing/checkout`, { plan }),
    verifyPayment: (t, reference) => post(`/api/v1/tenants/${t}/billing/verify`, { reference }),
    renameWorkspace: (tenantId, name) => request(`/api/v1/tenants/${tenantId}/workspace`, { method: 'PATCH', body: JSON.stringify({ name }) }),
    portal: {
      me: (t) => request(`/api/v1/tenants/${t}/portal/me`),
      profile: (t) => request(`/api/v1/tenants/${t}/portal/profile`),
      saveProfile: (t, input) => request(`/api/v1/tenants/${t}/portal/profile`, { method: 'PUT', body: JSON.stringify(input) }),
      setPhone: (t, phone, email) => request(`/api/v1/tenants/${t}/portal/phone`, { method: 'PUT', body: JSON.stringify(email === undefined ? { phone } : { phone, email }) }),
      orders: (t) => request(`/api/v1/tenants/${t}/portal/orders`),
      summary: (t) => request(`/api/v1/tenants/${t}/portal/summary`),
      claims: (t) => request(`/api/v1/tenants/${t}/portal/claims`),
      openClaim: (t, input) => post(`/api/v1/tenants/${t}/portal/claims`, input),
      statement: (t, from, to) => request(`/api/v1/tenants/${t}/portal/statement?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`),
      downloadStatement: (t, from, to) => download(`/api/v1/tenants/${t}/portal/statement.csv?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`),
      createOrder: (t, input, key) => post(`/api/v1/tenants/${t}/portal/orders`, input, { 'Idempotency-Key': key }),
    },
    platform: {
      companies: () => request('/api/v1/platform/tenants'),
      renameCompany: (tenantId, name) => post(`/api/v1/platform/tenants/${tenantId}/name`, { name }),
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
