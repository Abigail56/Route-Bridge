import './globals.css';
import { AuthProvider } from '../lib/auth';
import { ThemeProvider } from '../components/theme-provider';
import { SessionGuard } from '../components/session-guard';
import { AppInstallSetup } from '../components/install-app';
import type { Metadata, Viewport } from 'next';

// Installable as an app on phones and computers (public/app.webmanifest). The rider pages under /driver keep their own manifest.
export const metadata: Metadata = {
  title: 'RouteBridge | Operations Console',
  description: 'Nigeria-first regional last-mile logistics control plane',
  manifest: '/app.webmanifest',
  icons: { icon: '/app-icon-192.png', apple: '/apple-touch-icon.png' },
  appleWebApp: { capable: true, title: 'RouteBridge', statusBarStyle: 'black-translucent' },
};

export const viewport: Viewport = { themeColor: '#0f172a', width: 'device-width', initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  // the sidebar's remembered state is put on <html> before the page paints, so a closed sidebar never flashes open
  const remember = "try{if(localStorage.getItem('rb_sidebar')==='closed')document.documentElement.dataset.sidebar='closed'}catch(e){}";
  return <html lang="en" suppressHydrationWarning><head><script dangerouslySetInnerHTML={{ __html: remember }} /></head><body><AuthProvider><ThemeProvider>{children}</ThemeProvider><SessionGuard /><AppInstallSetup /></AuthProvider></body></html>;
}
