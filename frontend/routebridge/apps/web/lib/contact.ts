// RouteBridge Logistics' public contact details: the landing page's "Get in touch", and the WhatsApp button new shops and riders
// use to send their ID to the Admin. The phone number is also the WhatsApp number.
export const CONTACT_EMAIL = 'chukwuabigail307@gmail.com';
export const CONTACT_PHONE = { display: '0906 046 1720', tel: '+2349060461720', whatsapp: '2349060461720' };

/** A wa.me link that opens WhatsApp with the message already typed, addressed to RouteBridge. */
export const whatsappLink = (text: string): string => `https://wa.me/${CONTACT_PHONE.whatsapp}?text=${encodeURIComponent(text)}`;
