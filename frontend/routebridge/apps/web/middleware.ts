import { NextResponse, type NextRequest } from 'next/server';

// Public: the front page "/", sign-in/up and password reset, the customer tracking page, the driver PWA (it authenticates with its
// own device token), and the PWA files. Everything else needs a signed-in session.
// A path is public only if it is exactly one of these or sits under it: /driver is public, /drivers (the console page) is not.
// /api is the API itself, reached through the built-in proxy in demo mode; the API checks every request's own session.
const PUBLIC_PATH = /^\/$|^\/(?:sign-in|sign-up|forgot-password|reset-password|track|driver|api|sw\.js|manifest\.webmanifest|favicon\.ico)(?:\/|$)/;

// The session cookie is httpOnly and signed by the API, which checks it on every call. Here only its presence is looked at, to send
// signed-out visitors to the sign-in page instead of an empty console; a forged cookie gets past this page check but no data.
export function middleware(request: NextRequest) {
  if (PUBLIC_PATH.test(request.nextUrl.pathname) || request.cookies.has('rb_session')) return NextResponse.next();
  const signIn = request.nextUrl.clone();
  signIn.pathname = '/sign-in';
  signIn.search = `?next=${encodeURIComponent(request.nextUrl.pathname + request.nextUrl.search)}`;
  return NextResponse.redirect(signIn);
}

export const config = { matcher: ['/((?!_next|.*\\..*).*)'] };
