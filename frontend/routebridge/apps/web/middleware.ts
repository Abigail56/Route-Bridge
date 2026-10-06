import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server';
import { NextResponse } from 'next/server';

// Public: sign-in/up, the customer tracking page, the driver PWA (it authenticates with its own device token),
// and the PWA files. Everything else needs a Clerk session.
const isProtected = createRouteMatcher(['/((?!sign-in|sign-up|track|driver|sw.js|manifest.webmanifest|_next|favicon.ico).*)']);

// clerkMiddleware throws on every request when no publishable key is configured (local demo mode), so only
// install it when Clerk is configured; otherwise let requests through.
const clerkConfigured = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

export default clerkConfigured
  ? clerkMiddleware((auth, request) => {
      if (isProtected(request)) auth.protect();
    })
  : () => NextResponse.next();

export const config = { matcher: ['/((?!_next|.*\\..*).*)'] };
