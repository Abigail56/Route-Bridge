'use client';

import { useCallback, useEffect, useState } from 'react';
import type { ApiClient, MyTenant, Profile } from './api';
import { friendlyMessage } from './api';

const envTenantId = process.env.NEXT_PUBLIC_ROUTE_BRIDGE_TENANT_ID;

export type TenantStatus = 'loading' | 'ready' | 'needs-workspace' | 'error';

/**
 * Resolves the active workspace: the explicit env override first, else the caller's first membership.
 * A signed-in user with no workspace yet gets status `needs-workspace` so the console can show first-run setup.
 */
export function useTenant(api: ApiClient) {
  const [tenant, setTenant] = useState<MyTenant | null>(envTenantId ? { tenant_id: envTenantId, name: '', role: '' } : null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [status, setStatus] = useState<TenantStatus>(envTenantId ? 'ready' : 'loading');
  const [error, setError] = useState('');
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (envTenantId) return;
    let active = true;
    api.getProfile()
      .then((result) => {
        if (!active) return;
        setProfile(result);
        if (result.tenants.length) { setTenant(result.tenants[0]); setStatus('ready'); setError(''); }
        else { setTenant(null); setStatus('needs-workspace'); }
      })
      .catch((exc) => { if (active) { setError(friendlyMessage(exc)); setStatus('error'); } });
    return () => { active = false; };
  }, [api, tick]);

  const reload = useCallback(() => { setStatus('loading'); setTick((value) => value + 1); }, []);
  return { tenant, profile, status, error, reload };
}
