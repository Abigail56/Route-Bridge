import { clerkMiddleware } from '@clerk/nextjs/server';
import { NextResponse } from 'next/server';

// Public: sign-in/up, the customer tracking page, the driver PWA (it authenticates with its own device token),
// and the PWA files. Everything else needs a Clerk session.
// A path is public only if it is exactly one of these or sits under it: /driver is public, /drivers (the console page) is not.
// /api is the API itself, reached through the built-in proxy in demo mode; the API checks every request's own token.
const PUBLIC_PATH = /^\/(?:sign-in|sign-up|track|driver|api|sw\.js|manifest\.webmanifest|favicon\.ico)(?:\/|$)/;
const isProtected = (request: { nextUrl: { pathname: string } }) => !PUBLIC_PATH.test(request.nextUrl.pathname);

// clerkMiddleware throws on every request when no publishable key is configured (local demo mode), so only
// install it when Clerk is configured; otherwise let requests through.
const clerkConfigured = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

export default clerkConfigured
  ? clerkMiddleware((auth, request) => {
      if (isProtected(request)) auth.protect();
    })
  : () => NextResponse.next();

export const config = { matcher: ['/((?!_next|.*\\..*).*)'] };
