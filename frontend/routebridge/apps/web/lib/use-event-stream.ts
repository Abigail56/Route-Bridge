'use client';

import { useEffect, useRef, useState } from 'react';
import { API_BASE_URL, readError } from './api';

export type StreamState = 'connecting' | 'live' | 'offline';

/** Minimal SSE reader over fetch (EventSource cannot send Authorization headers). */
export function useEventStream(tenantId: string | undefined, getToken: () => Promise<string | null>, onEvent: (type: string) => void): StreamState {
  const [state, setState] = useState<StreamState>('connecting');
  const handler = useRef(onEvent);
  handler.current = onEvent;
  const tokenFn = useRef(getToken);
  tokenFn.current = getToken;

  useEffect(() => {
    if (!tenantId) return;
    const controller = new AbortController();
    let lastEventId = '';
    let attempt = 0;

    async function run() {
      while (!controller.signal.aborted) {
        try {
          setState('connecting');
          const token = await tokenFn.current();
          const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
          if (lastEventId) headers['Last-Event-ID'] = lastEventId;
          const response = await fetch(`${API_BASE_URL}/api/v1/tenants/${tenantId}/events`, { headers, signal: controller.signal });
          if (!response.ok || !response.body) {
            const error = await readError(response);
            if (error.status === 401 || error.status === 403) { setState('offline'); return; } // retrying cannot fix auth
            throw error;
          }
          setState('live');
          attempt = 0;
          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            let boundary = buffer.indexOf('\n\n');
            while (boundary >= 0) {
              const lines = buffer.slice(0, boundary).split('\n');
              buffer = buffer.slice(boundary + 2);
              boundary = buffer.indexOf('\n\n');
              let type = '';
              for (const line of lines) {
                if (line.startsWith('id:')) lastEventId = line.slice(3).trim();
                else if (line.startsWith('event:')) type = line.slice(6).trim();
              }
              if (type) handler.current(type); // heartbeat comments carry no event type
            }
          }
        } catch {
          if (controller.signal.aborted) return;
        }
        setState('offline');
        attempt += 1;
        await new Promise((resolve) => setTimeout(resolve, Math.min(30000, 1000 * 2 ** attempt)));
      }
    }
    run();
    return () => controller.abort();
  }, [tenantId]);

  return state;
}
