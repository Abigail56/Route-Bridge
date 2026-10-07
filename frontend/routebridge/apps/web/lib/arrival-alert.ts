/** The customer's "tell me when my rider arrives" alert. Pure decisions live here so they can be tested; the page only wires them to the browser. */
export const ALERT_STATUSES = ['arrived', 'delivered'] as const;

/** Alert only on a real change INTO an alert status, never on the first load of a page whose parcel is already there. */
export function shouldAlert(previous: string | null, next: string): boolean {
  return previous !== null && previous !== next && (ALERT_STATUSES as readonly string[]).includes(next);
}

export function alertText(status: string, merchant: string | null, reference: string | null): { title: string; body: string } {
  const what = reference ? `order ${reference}` : 'your order';
  const lead = merchant ? `${merchant}: ` : '';
  const sentence = (text: string) => (merchant ? text : text.charAt(0).toUpperCase() + text.slice(1));
  return status === 'delivered'
    ? { title: 'Delivered', body: lead + sentence(`${what} was delivered. Thank you!`) }
    : { title: 'Your rider has arrived', body: lead + sentence(`your rider is outside with ${what}. Please be ready to receive it.`) };
}
