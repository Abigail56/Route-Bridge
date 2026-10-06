import type { Metadata, Viewport } from 'next';

export const metadata: Metadata = {
  title: 'RouteBridge Driver',
  description: 'Offline-first delivery app for RouteBridge drivers',
  manifest: '/manifest.webmanifest',
};

export const viewport: Viewport = { themeColor: '#173438', width: 'device-width', initialScale: 1, maximumScale: 1 };

export default function DriverLayout({ children }: { children: React.ReactNode }) {
  return children;
}
