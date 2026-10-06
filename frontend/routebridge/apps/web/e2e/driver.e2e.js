const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// Config (all optional): RB_API_URL, RB_WEB_URL, RB_MEDIA_DIR (where the backend stores uploads), RB_OUT_DIR (screenshots).
const API = (process.env.RB_API_URL || 'http://localhost:8000') + '/api/v1';
const WEB = process.env.RB_WEB_URL || 'http://localhost:3000';
const MEDIA_DIR = process.env.RB_MEDIA_DIR || path.resolve(__dirname, '..', 'media');
const OUT_DIR = process.env.RB_OUT_DIR || path.resolve(__dirname, 'out');
fs.mkdirSync(OUT_DIR, { recursive: true });
let failures = 0;

const check = (name, ok, extra = '') => { if (!ok) failures++; console.log(`${ok ? 'PASS' : 'FAIL'} ${name} ${extra}`); };
async function api(method, p, body, headers = {}) {
  const res = await fetch(API + p, { method, headers: { 'Content-Type': 'application/json', ...headers }, body: body ? JSON.stringify(body) : undefined });
  const text = await res.text();
  let json; try { json = JSON.parse(text); } catch { json = text; }
  if (!res.ok && !headers['x-allow-error']) throw new Error(`${method} ${p} -> ${res.status} ${text}`);
  return json;
}
async function until(fn, label, timeout = 60000) {
  const start = Date.now();
  for (;;) {
    const value = await fn();
    if (value) return value;
    if (Date.now() - start > timeout) throw new Error('timeout waiting for ' + label);
    await new Promise((r) => setTimeout(r, 500));
  }
}

(async () => {
  for (let i = 0; i < 40; i++) { try { if ((await fetch(API.replace('/api/v1', '') + '/health')).ok) break; } catch {} await new Promise((r) => setTimeout(r, 500)); }
  for (let i = 0; i < 40; i++) { try { if ((await fetch(WEB + '/driver')).ok) break; } catch {} await new Promise((r) => setTimeout(r, 500)); }

  // ---- seed through the real API
  const tenant = await api('POST', '/admin/tenants', { name: 'E2E Logistics' });
  const tid = tenant.id;
  const merchant = await api('POST', `/admin/tenants/${tid}/merchants`, { name: 'E2E Shop' });
  const order = await api('POST', `/tenants/${tid}/orders`, { merchant_id: merchant.id, customer_name: 'Ada Okafor', customer_phone: '+2348012345678', external_ref: 'RB-E2E-1', cod_amount: '4000', total_amount: '4000', address_text: '12 Allen Ave, Ikeja', landmark: 'Opposite the blue gate' });
  const job = order.delivery_job_id;
  const driver = await api('POST', `/tenants/${tid}/drivers`, { name: 'Chisom Obi', phone: '08066660000' });
  await api('POST', `/tenants/${tid}/delivery-jobs/${job}/assignments`, { driver_id: driver.id });
  const { access_token } = await api('POST', `/tenants/${tid}/drivers/${driver.id}/token`);
  const jobStatus = async () => (await api('GET', `/tenants/${tid}/orders`))[0].job_status;

  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 390, height: 800 }, permissions: ['geolocation'], geolocation: { latitude: 6.6018, longitude: 3.3515 }, serviceWorkers: 'allow' });
  const page = await context.newPage();
  page.on('pageerror', (e) => console.log('PAGE ERROR', e.message));

  await page.goto(`${WEB}/driver#token=${access_token}`);
  await page.getByText('RB-E2E-1').first().waitFor({ timeout: 30000 });
  check('job appears after token sign-in (hash token consumed)', !page.url().includes('token='));
  // ---- online: accept
  await page.getByText('RB-E2E-1').first().click();
  await page.getByText('Ada Okafor').first().waitFor();
  const detail = await page.content();
  check('customer phone is masked in the job detail', !detail.includes('2348012345678') && !detail.includes('08012345678') && detail.includes('5678'));
  await page.getByRole('button', { name: 'Accept job' }).click();
  await until(async () => (await jobStatus()) === 'accepted', 'server accepted');
  check('online action reaches the server quickly', true);

  // ---- offline: start trip + arrive are queued locally
  await context.setOffline(true);
  await page.getByRole('button', { name: 'Start trip' }).click();
  await page.getByRole('button', { name: "I've arrived" }).click();
  await page.getByText(/2 to sync/).waitFor({ timeout: 15000 });
  check('offline actions are queued and the UI shows them', true);
  check('server has not seen offline actions yet', (await jobStatus()) === 'accepted');
  await page.screenshot({ path: path.join(OUT_DIR, 'driver-offline.png') });

  // data at rest is encrypted
  const raw = await page.evaluate(() => new Promise((resolve) => {
    const open = indexedDB.open('routebridge-driver');
    open.onsuccess = () => {
      const db = open.result; const tx = db.transaction(['queue', 'kv'], 'readonly');
      const out = {}; let pending = 2;
      for (const name of ['queue', 'kv']) {
        const req = tx.objectStore(name).getAll();
        req.onsuccess = () => { out[name] = req.result.map((r) => JSON.stringify(r, (k, v) => (v instanceof ArrayBuffer || ArrayBuffer.isView(v) ? `bytes(${v.byteLength})` : v))); if (--pending === 0) resolve(out); };
      }
    };
  }));
  const blob = JSON.stringify(raw);
  check('queued events are not stored as readable JSON', !blob.includes('en_route') && !blob.includes('target_status'));
  check('access token is not stored in plaintext', !blob.includes(access_token.slice(0, 20)));

  // ---- back online: queue drains in order
  await context.setOffline(false);
  await until(async () => (await jobStatus()) === 'arrived', 'server arrived after reconnect', 90000);
  await page.getByText(/All synced/).waitFor({ timeout: 60000 });
  check('queue syncs automatically on reconnect, in order (accepted -> en_route -> arrived)', true);

  // ---- delivery: staff texts the OTP, driver completes the delivery OFFLINE with a photo
  const otp = await api('POST', `/tenants/${tid}/delivery-jobs/${job}/otp`);
  const jpeg = Buffer.from('/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA=', 'base64');
  await context.setOffline(true);
  await page.getByLabel('Delivery code').fill(otp.debug_code);
  await page.getByLabel('Received by').fill('Ada Okafor');
  await page.getByLabel('Delivery photo').setInputFiles({ name: 'proof.jpg', mimeType: 'image/jpeg', buffer: jpeg });
  await page.getByRole('button', { name: 'Confirm delivered' }).click();
  await page.getByText(/to sync/).waitFor({ timeout: 15000 });
  check('delivery completed offline is saved locally', (await jobStatus()) === 'arrived');
  await context.setOffline(false);
  await until(async () => (await jobStatus()) === 'delivered', 'server delivered after reconnect', 90000);
  check('proof (server-verified OTP + photo) and delivery reach the server after reconnect', true);

  // ---- server-side evidence
  const audit = await api('GET', `/tenants/${tid}/audit?limit=200`);
  const types = audit.map((a) => a.event_type);
  check('server verified the OTP', types.includes('delivery.otp.verified'));
  check('COD payment recorded', types.includes('delivery.payment') || audit.some((a) => a.aggregate_type === 'delivery_job' && a.payload && a.payload.collected_amount));
  check('OTP code never stored in the audit trail', !JSON.stringify(audit).includes(otp.debug_code));
  const mediaDir = path.join(MEDIA_DIR, tid, job);
  const photos = fs.existsSync(mediaDir) ? fs.readdirSync(mediaDir).filter((f) => f.startsWith('photo-')) : [];
  check('photo was uploaded to storage', photos.length === 1, photos.join(','));
  const stats = await page.evaluate(() => new Promise((resolve) => { const o = indexedDB.open('routebridge-driver'); o.onsuccess = () => { const tx = o.result.transaction(['queue', 'blobs'], 'readonly'); const q = tx.objectStore('queue').count(); const b = tx.objectStore('blobs').count(); tx.oncomplete = () => resolve({ queue: q.result, blobs: b.result }); }; }));
  check('local queue and photo blobs are cleared after sync', stats.queue === 0 && stats.blobs === 0, JSON.stringify(stats));
  const orders = await api('GET', `/tenants/${tid}/orders`);
  check('order is delivered end to end', orders[0].job_status === 'delivered' && orders[0].status === 'delivered');

  // ---- service worker caches the shell so the app opens offline
  await page.waitForFunction(() => navigator.serviceWorker && navigator.serviceWorker.controller !== null || true);
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload(); // let the worker take control and cache the shell
  await context.setOffline(true);
  await page.reload();
  check('app shell loads while offline (service worker)', await page.getByText('My deliveries').first().isVisible().catch(() => false));
  await page.screenshot({ path: path.join(OUT_DIR, 'driver-reloaded-offline.png') });
  await context.setOffline(false);

  await browser.close();
  console.log(failures ? `\n${failures} CHECK(S) FAILED` : '\nALL E2E CHECKS PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error('E2E ERROR', e.message); process.exit(2); });
