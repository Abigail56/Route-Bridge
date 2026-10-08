/** Links that open the staff member's own WhatsApp, text app or dialer with the customer's number already filled in. */

/** 08031112222, +234 803 111 2222, 2348031112222 and 8031112222 all become 2348031112222 (digits only, no +). */
export function toInternational(phone: string, dialCode = '234'): string {
  const digits = phone.replace(/\D/g, '');
  if (phone.trim().startsWith('+')) return digits;
  if (digits.startsWith('00')) return digits.slice(2);
  if (digits.startsWith(dialCode) && digits.length >= dialCode.length + 8) return digits;
  if (digits.startsWith('0') && digits.length >= 10 && digits.length <= 12) return dialCode + digits.slice(1);
  if (digits.length >= 9 && digits.length <= 10) return dialCode + digits;
  return digits;
}

export const whatsappLink = (phone: string, text: string) => `https://wa.me/${toInternational(phone)}?text=${encodeURIComponent(text)}`;
export const smsLink = (phone: string, text: string) => `sms:+${toInternational(phone)}?&body=${encodeURIComponent(text)}`;
export const callLink = (phone: string) => `tel:+${toInternational(phone)}`;
