'use client';

// Installing RouteBridge as an app on a phone or computer (public/app.webmanifest + public/sw.js). Android and desktop Chrome/Edge
// hand the page an install offer, which the Install app button uses; iPhone Safari has no offer, so there the button explains
// Share > Add to Home Screen. Once installed (opened from its icon) the button hides itself.
import { useEffect, useState } from 'react';

type InstallOffer = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }> };

let offer: InstallOffer | null = null;
const listeners = new Set<() => void>();
const changed = () => listeners.forEach((listener) => listener());

/** Mounted once for the whole site: registers the offline worker and keeps the browser's install offer for the button. */
export function AppInstallSetup() {
  useEffect(() => {
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => undefined);
    const keep = (event: Event) => { event.preventDefault(); offer = event as InstallOffer; changed(); };
    const installed = () => { offer = null; changed(); };
    window.addEventListener('beforeinstallprompt', keep);
    window.addEventListener('appinstalled', installed);
    return () => { window.removeEventListener('beforeinstallprompt', keep); window.removeEventListener('appinstalled', installed); };
  }, []);
  return null;
}

const runningAsApp = () => window.matchMedia('(display-mode: standalone)').matches || (navigator as Navigator & { standalone?: boolean }).standalone === true;
const isIphone = () => /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);

/** "Install app": shown only where installing is possible and RouteBridge is not already running as an app. */
export function InstallButton({ className = 'button secondary', label = 'Install app' }: { className?: string; label?: string }) {
  const [state, setState] = useState<'hidden' | 'offer' | 'iphone'>('hidden');
  const [help, setHelp] = useState(false);
  useEffect(() => {
    const look = () => setState(runningAsApp() ? 'hidden' : offer ? 'offer' : isIphone() ? 'iphone' : 'hidden');
    look();
    listeners.add(look);
    return () => { listeners.delete(look); };
  }, []);
  if (state === 'hidden') return null;
  async function install() {
    if (state === 'iphone') { setHelp((open) => !open); return; }
    if (!offer) return;
    await offer.prompt();
    await offer.userChoice.catch(() => undefined);
    offer = null;
    changed();
  }
  return <span className="install-app">
    <button type="button" className={className} onClick={install} aria-expanded={state === 'iphone' ? help : undefined}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12m0 0-4-4m4 4 4-4M5 17v3h14v-3" /></svg>{label}
    </button>
    {help && <span className="install-help" role="note">On iPhone or iPad: tap the <b>Share</b> button in Safari (the square with an arrow), then <b>Add to Home Screen</b>.</span>}
  </span>;
}
