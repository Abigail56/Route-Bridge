/** Links that open the phone's own navigation apps for a drop-off. A pin is used when the job has one, otherwise the address text. */
export type NavTarget = { latitude: number | null; longitude: number | null; address: string | null };

export function navigationLinks(target: NavTarget): { google: string; waze: string; apple: string } {
  const pin = target.latitude !== null && target.longitude !== null ? `${target.latitude},${target.longitude}` : null;
  const text = encodeURIComponent(target.address ?? '');
  return {
    google: pin ? `https://www.google.com/maps/dir/?api=1&destination=${pin}&travelmode=driving` : `https://www.google.com/maps/search/?api=1&query=${text}`,
    waze: pin ? `https://waze.com/ul?ll=${pin}&navigate=yes` : `https://waze.com/ul?q=${text}&navigate=yes`,
    apple: pin ? `https://maps.apple.com/?daddr=${pin}&dirflg=d` : `https://maps.apple.com/?q=${text}`,
  };
}
