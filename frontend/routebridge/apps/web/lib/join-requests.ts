import type { JoinRequest } from './api';

/** A request counts as new each time it is sent: "Send again" (allowed after a minute) rings the Admin again. */
const keyOf = (row: Pick<JoinRequest, 'id' | 'sent_at'>) => `${row.id}@${row.sent_at}`;

export type SeenRequests = Set<string>;
export const toSeen = (rows: Pick<JoinRequest, 'id' | 'sent_at'>[]): SeenRequests => new Set(rows.map(keyOf));

/** Requests that arrived since the last look. The first look (seen = null) announces nothing, so opening the console stays quiet. */
export function freshRequests<T extends Pick<JoinRequest, 'id' | 'sent_at'>>(seen: SeenRequests | null, rows: T[]): T[] {
  if (seen === null) return [];
  return rows.filter((row) => !seen.has(keyOf(row)));
}

/** "Ada Foods wants to join as a shop", "Musa Bello wants to join as a driver". */
export function requestText(row: Pick<JoinRequest, 'role' | 'shop_name' | 'full_name' | 'email'>): string {
  const who = (row.role === 'merchant_user' ? row.shop_name : null) || row.full_name || row.email || 'Someone';
  return `${who} wants to join as ${row.role === 'merchant_user' ? 'a shop' : 'a driver'}`;
}
