import './globals.css';
import { AuthProvider } from '../lib/auth';
import { ThemeProvider } from '../components/theme-provider';
import { SessionGuard } from '../components/session-guard';

export const metadata = {
  title: 'RouteBridge | Operations Console',
  description: 'Nigeria-first regional last-mile logistics control plane'
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  // the sidebar's remembered state is put on <html> before the page paints, so a closed sidebar never flashes open
  const remember = "try{if(localStorage.getItem('rb_sidebar')==='closed')document.documentElement.dataset.sidebar='closed'}catch(e){}";
  return <html lang="en" suppressHydrationWarning><head><script dangerouslySetInnerHTML={{ __html: remember }} /></head><body><AuthProvider><ThemeProvider>{children}</ThemeProvider><SessionGuard /></AuthProvider></body></html>;
}
