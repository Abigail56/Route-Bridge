'use client';

import type { StreamState } from '../lib/use-event-stream';

export function LiveStreamStatus({ state }: { state: StreamState }) {
  const label = { connecting: 'Connecting', live: 'Live', offline: 'Offline' }[state];
  return <span className={`stream-status stream-${state}`}><i /> {label}</span>;
}
