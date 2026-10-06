'use client';

import { UserButton } from '@clerk/nextjs';

/** Clerk's account menu (profile and sign out). Only rendered when Clerk is configured (see page.tsx). */
export function AccountMenu() {
  return <UserButton afterSignOutUrl="/sign-in" />;
}
