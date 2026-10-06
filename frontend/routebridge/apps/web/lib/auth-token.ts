'use client';

import { useAuth } from '@clerk/nextjs';
import { useCallback, useRef } from 'react';

const clerkEnabled = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);
const noToken = async (): Promise<string | null> => null;
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Returns a stable `getToken` for API calls.
 *
 * With Clerk configured it WAITS (up to ~10s) for Clerk to finish loading and be signed in before answering. Without that wait, the
 * console's first requests fire on mount with no token and the API rejects them with 401. When Clerk is not
 * configured (local demo mode) it resolves to null and the API's development bypass applies.
 * `clerkEnabled` is a build-time constant, so the hook call order never changes between renders.
 */
export function useGetToken(): (options?: { skipCache?: boolean }) => Promise<string | null> {
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const auth = clerkEnabled ? useAuth() : null;
  const latest = useRef(auth);
  latest.current = auth;
  // eslint-disable-next-line react-hooks/rules-of-hooks
  return useCallback(async (options?: { skipCache?: boolean }) => {
    if (!clerkEnabled) return noToken();
    // Right after a sign-in redirect Clerk can report "loaded" a moment before "signed in", so wait for both.
    for (let i = 0; i < 100 && !(latest.current?.isLoaded && latest.current.isSignedIn); i++) await sleep(100);
    const current = latest.current;
    return current?.isLoaded && current.isSignedIn ? current.getToken(options?.skipCache ? { skipCache: true } : undefined) : null;
  }, []);
}
