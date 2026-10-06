import type { OrderRead } from './api';

/** UI status. Backend job statuses are folded into these buckets (see toStatus). */
export type Status = 'pending' | 'assigned' | 'en_route' | 'arrived' | 'delivered' | 'exception';
export type Confidence = 'High' | 'Medium' | 'Low';
export type Job = {
  id: string; order: string; customer: string; merchant: string; area: string;
  landmark: string; amount: number; status: Status; driver?: string;
  confidence: Confidence; time: string; createdAt: string;
  jobId: string | null; rawStatus: string;
  orderId: string; score: number | null; plusCode: string | null; trackingToken: string | null;
  windowStart: string | null; windowEnd: string | null; corrected: boolean;
};

/** Mirrors the backend ALLOWED_TRANSITIONS so the UI only offers moves the API accepts. */
export const NEXT_STATUSES: Record<string, string[]> = {
  pending: ['cancelled'],
  assigned: ['accepted', 'cancelled'],
  accepted: ['en_route', 'cancelled'],
  en_route: ['arrived', 'cancelled'],
  arrived: ['delivered', 'failed_attempt', 'cancelled'],
  failed_attempt: ['rescheduled', 'returned', 'cancelled'],
  rescheduled: ['cancelled'],
};

/**
 * Backend job statuses: pending, assigned, accepted, en_route, arrived, delivered,
 * failed_attempt, rescheduled, returned, cancelled. The UI "exception" bucket covers
 * everything that needs human attention.
 */
export function toStatus(jobStatus: string | null | undefined): Status {
  switch (jobStatus) {
    case 'assigned':
    case 'accepted': return 'assigned';
    case 'en_route': return 'en_route';
    case 'arrived': return 'arrived';
    case 'delivered': return 'delivered';
    case 'failed_attempt':
    case 'rescheduled':
    case 'returned':
    case 'cancelled': return 'exception';
    default: return 'pending';
  }
}

export function bandFromScore(score: number | null | undefined): Confidence | null {
  if (score === null || score === undefined) return null;
  return score >= 70 ? 'High' : score >= 45 ? 'Medium' : 'Low';
}

export function toConfidence(value: string | null | undefined): Confidence {
  if (value === 'driver_confirmed' || value === 'customer_confirmed') return 'High';
  if (value === 'geocoded') return 'Medium';
  return 'Low';
}

export function toAmount(value: string | number | null | undefined): number {
  const parsed = typeof value === 'number' ? value : parseFloat(value ?? '0');
  return Number.isFinite(parsed) ? parsed : 0;
}

export function timeAgo(iso: string, now = Date.now()): string {
  const hasZone = iso.endsWith('Z') || /[+-]\d\d:\d\d$/.test(iso);
  const created = Date.parse(hasZone ? iso : `${iso}Z`);
  const minutes = Math.max(0, Math.round((now - created) / 60000));
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  return `${Math.round(hours / 24)} d ago`;
}

export function toJob(order: OrderRead): Job {
  return {
    id: order.delivery_job_id ?? order.id,
    order: order.external_ref,
    customer: order.customer_name ?? 'Unknown customer',
    merchant: order.merchant_name ?? '',
    area: order.address_text ?? '—',
    landmark: order.landmark ?? '',
    amount: toAmount(order.cod_amount),
    status: toStatus(order.job_status),
    driver: order.driver_name ?? undefined,
    confidence: bandFromScore(order.location_score) ?? toConfidence(order.location_confidence),
    time: timeAgo(order.created_at),
    createdAt: order.created_at,
    jobId: order.delivery_job_id,
    rawStatus: order.job_status ?? 'pending',
    orderId: order.id,
    score: order.location_score,
    plusCode: order.plus_code,
    trackingToken: order.tracking_token,
    windowStart: order.window_start,
    windowEnd: order.window_end,
    corrected: order.location_corrected,
  };
}
