'use client';

import { useEffect, useState } from 'react';
import type { DriverClient } from '../lib/driver/api';
import { currentPushState, disablePush, enablePush, type PushState } from '../lib/driver/push';

const TEXT: Record<PushState, string> = {
  unsupported: '',
  unavailable: '',
  blocked: 'Alerts are blocked for this app. Allow notifications in your phone settings to get them.',
  off: 'Get an alert on this phone when dispatch gives you a delivery.',
  on: 'Alerts are on for this phone.',
};

/** One line in the driver app: turn phone alerts on or off. Hidden when the phone or the server cannot do it. */
export function DriverPush({ client }: { client: DriverClient }) {
  const [state, setState] = useState<PushState>('unsupported');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { currentPushState(client).then(setState).catch(() => setState('unsupported')); }, [client]);
  if (state === 'unsupported' || state === 'unavailable') return null;

  async function toggle() {
    setBusy(true); setError('');
    try { setState(state === 'on' ? await disablePush(client) : await enablePush(client)); } catch (exc) { setError(exc instanceof Error ? exc.message : 'Could not change alerts. Try again when you have signal.'); } finally { setBusy(false); }
  }
  return <div style={{ fontSize: 13, margin: '0 0 10px', display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
    <span>{TEXT[state]}</span>
    {state !== 'blocked' && <button type="button" onClick={toggle} disabled={busy} style={{ padding: '6px 12px', borderRadius: 8, border: '1px solid currentColor', background: 'transparent', color: 'inherit', font: 'inherit' }}>{busy ? 'Working…' : state === 'on' ? 'Turn off' : 'Turn on alerts'}</button>}
    {error && <span role="alert" style={{ color: '#b3261e' }}>{error}</span>}
  </div>;
}
