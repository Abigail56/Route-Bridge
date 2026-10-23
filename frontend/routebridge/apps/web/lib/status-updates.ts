/** Works out which orders changed status between two looks at the list, and says it in plain words for the shop. */
export type Snapshot = Record<string, string>;
type Row = { id: string; external_ref: string; status: string; code_verified?: boolean };
export type Change = { id: string; ref: string; to: string; text: string; tone: 'info' | 'good' | 'warn' };

export const toSnapshot = (rows: Row[]): Snapshot => Object.fromEntries(rows.map((row) => [row.id, row.status]));

export function changeText(ref: string, status: string, codeVerified = false): { text: string; tone: Change['tone'] } {
  switch (status) {
    case 'assigned': return { text: `Order ${ref} was given to a rider`, tone: 'info' };
    case 'accepted': return { text: `The rider accepted order ${ref}`, tone: 'info' };
    case 'en_route': return { text: `Order ${ref} is on the way`, tone: 'info' };
    case 'arrived': return { text: `The rider is at the customer's door with order ${ref}`, tone: 'info' };
    case 'delivered': return { text: codeVerified ? `Order ${ref} was delivered. The customer's code was checked ✓` : `Order ${ref} was delivered`, tone: 'good' };
    case 'failed_attempt': return { text: `Delivery of order ${ref} failed. We will be in touch`, tone: 'warn' };
    case 'rescheduled': return { text: `Order ${ref} was rescheduled`, tone: 'warn' };
    case 'returned': return { text: `Order ${ref} is being returned to you`, tone: 'warn' };
    case 'cancelled': return { text: `Order ${ref} was cancelled`, tone: 'warn' };
    default: return { text: `Order ${ref} changed to ${status.replace(/_/g, ' ')}`, tone: 'info' };
  }
}

/** Orders that were not on the screen at the last look: a shop has just placed them (the console chimes for these).
 *  The first look (no earlier snapshot) announces nothing, so opening the console never plays a burst of old orders. */
// "₦5,000" as Nigerians write it; whole naira
const naira = (amount: number) => `₦${Math.round(amount).toLocaleString('en-NG')}`;

/** A new order's line, with its cash on delivery when the shop asked for one: "New order RB-104 from Ada Foods · ₦5,000 cash on delivery". */
export function newOrderText(ref: string, merchant?: string | null, cod?: number | null): string {
  return `New order ${ref}${merchant ? ` from ${merchant}` : ''}${cod && cod > 0 ? ` · ${naira(cod)} cash on delivery` : ''}`;
}

export function newOrders(previous: Snapshot | null, rows: (Row & { merchant?: string | null; cod?: number | null })[]): Change[] {
  if (!previous) return [];
  return rows
    .filter((row) => previous[row.id] === undefined)
    .map((row) => ({ id: row.id, ref: row.external_ref, to: 'new', text: newOrderText(row.external_ref, row.merchant, row.cod), tone: 'info' as const }));
}

/** The Admin's cash on delivery at a glance: what riders still have to collect, and what was collected on delivered orders. */
export function codTotals(jobs: { status: string; amount: number }[]): { toCollect: number; toCollectOrders: number; collected: number; collectedOrders: number } {
  const open = jobs.filter((job) => job.amount > 0 && job.status !== 'delivered' && job.status !== 'exception');
  const done = jobs.filter((job) => job.amount > 0 && job.status === 'delivered');
  const sum = (rows: { amount: number }[]) => rows.reduce((total, job) => total + job.amount, 0);
  return { toCollect: sum(open), toCollectOrders: open.length, collected: sum(done), collectedOrders: done.length };
}

/** Only orders already on the screen count: the first look (no earlier snapshot) and brand-new orders say nothing. */
export function statusChanges(previous: Snapshot | null, rows: Row[]): Change[] {
  if (!previous) return [];
  return rows
    .filter((row) => previous[row.id] !== undefined && previous[row.id] !== row.status)
    .map((row) => ({ id: row.id, ref: row.external_ref, to: row.status, ...changeText(row.external_ref, row.status, row.code_verified) }));
}
