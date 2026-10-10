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

/** Only orders already on the screen count: the first look (no earlier snapshot) and brand-new orders say nothing. */
export function statusChanges(previous: Snapshot | null, rows: Row[]): Change[] {
  if (!previous) return [];
  return rows
    .filter((row) => previous[row.id] !== undefined && previous[row.id] !== row.status)
    .map((row) => ({ id: row.id, ref: row.external_ref, to: row.status, ...changeText(row.external_ref, row.status, row.code_verified) }));
}
