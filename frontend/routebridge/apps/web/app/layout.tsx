import './globals.css';
import { ClerkProvider } from '@clerk/nextjs';
import { ThemeProvider } from '../components/theme-provider';

export const metadata = {
  title: 'RouteBridge | Operations Console',
  description: 'Nigeria-first regional last-mile logistics control plane'
};

// Clerk takes the heading from the application name set in its dashboard; this keeps the screens on-brand regardless.
const localization = {
  signIn: { start: { title: 'Sign in to RouteBridge', subtitle: 'Welcome back! Please sign in to continue.' } },
  signUp: { start: { title: 'Create your RouteBridge account', subtitle: 'Welcome! Please fill in the details to get started.' } }
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const publishableKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
  const content = <ThemeProvider>{children}</ThemeProvider>;
  return <html lang="en"><body>{publishableKey ? <ClerkProvider publishableKey={publishableKey} localization={localization}>{content}</ClerkProvider> : content}</body></html>;
}
