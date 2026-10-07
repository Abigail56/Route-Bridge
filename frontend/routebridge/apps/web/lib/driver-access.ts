/** Helpers for handing a driver their access: a link (and QR code) that opens the driver app already signed in. */

/** The driver app reads the token from the part of the address after #, which is never sent to any server. */
export function buildDriverLink(origin: string, token: string): string {
  return `${origin.replace(/\/+$/, '')}/driver#token=${encodeURIComponent(token)}`;
}

/** A phone cannot open "localhost": it means "this computer" on whatever device opens it. */
export function isLocalOnlyOrigin(origin: string): boolean {
  try {
    const host = new URL(origin).hostname;
    return host === 'localhost' || host === '127.0.0.1' || host === '::1' || host === '[::1]';
  } catch {
    return false;
  }
}

/** A WhatsApp message to the driver's own number, ready to send. Nigerian numbers may be written 0803..., +234803... or 234803... */
export function whatsappLink(phone: string, link: string, driverName: string, validHours: number): string {
  let digits = phone.replace(/\D/g, '');
  if (digits.startsWith('0')) digits = `234${digits.slice(1)}`;
  const message = `Hello ${driverName.split(' ')[0]}, here is your RouteBridge delivery link for today. Open it on your phone, allow location when asked, then tap "Add to Home screen". It works for ${validHours} hours:\n${link}`;
  return `https://wa.me/${digits}?text=${encodeURIComponent(message)}`;
}

export function validHours(expiresInSeconds: number): number {
  return Math.max(1, Math.round(expiresInSeconds / 3600));
}
