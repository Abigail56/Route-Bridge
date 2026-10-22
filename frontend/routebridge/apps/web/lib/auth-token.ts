'use client';

const noToken = async (): Promise<string | null> => null;

/**
 * The `getToken` the API client takes. The website's sign-in session is an httpOnly cookie the browser sends by itself
 * (see lib/auth.tsx), so there is no token to add; the hook stays so callers keep one shape.
 */
export function useGetToken(): () => Promise<string | null> {
  return noToken;
}
