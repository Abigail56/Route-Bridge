/** Web push helpers for the driver app. The server hands out a public key; the phone's browser makes a subscription we send back. */

export function urlBase64ToUint8Array(value: string): Uint8Array<ArrayBuffer> {
  const padded = value.padEnd(Math.ceil(value.length / 4) * 4, '=').replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(padded);
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

export function pushSupported(): boolean {
  return typeof window !== 'undefined' && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
}

export type PushApi = {
  pushKey: () => Promise<{ public_key: string | null }>;
  pushSubscribe: (subscription: { endpoint: string; keys: { p256dh: string; auth: string } }) => Promise<unknown>;
  pushUnsubscribe: (endpoint: string) => Promise<unknown>;
};

export type PushState = 'unsupported' | 'unavailable' | 'blocked' | 'off' | 'on';

async function registration() {
  return (await navigator.serviceWorker.getRegistration('/')) ?? (await navigator.serviceWorker.register('/sw.js'));
}

export async function currentPushState(api: PushApi): Promise<PushState> {
  if (!pushSupported()) return 'unsupported';
  if (Notification.permission === 'denied') return 'blocked';
  const { public_key } = await api.pushKey().catch(() => ({ public_key: null }));
  if (!public_key) return 'unavailable';
  const existing = await (await registration()).pushManager.getSubscription();
  return existing && Notification.permission === 'granted' ? 'on' : 'off';
}

export async function enablePush(api: PushApi): Promise<PushState> {
  if (!pushSupported()) return 'unsupported';
  const { public_key } = await api.pushKey();
  if (!public_key) return 'unavailable';
  if ((await Notification.requestPermission()) !== 'granted') return Notification.permission === 'denied' ? 'blocked' : 'off';
  const reg = await registration();
  const subscription = (await reg.pushManager.getSubscription()) ?? (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(public_key) }));
  const json = subscription.toJSON();
  if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) throw new Error('This phone could not create an alert subscription.');
  await api.pushSubscribe({ endpoint: json.endpoint, keys: { p256dh: json.keys.p256dh, auth: json.keys.auth } });
  return 'on';
}

export async function disablePush(api: PushApi): Promise<PushState> {
  if (!pushSupported()) return 'unsupported';
  const subscription = await (await registration()).pushManager.getSubscription();
  if (subscription) {
    await api.pushUnsubscribe(subscription.endpoint).catch(() => undefined);
    await subscription.unsubscribe();
  }
  return 'off';
}
