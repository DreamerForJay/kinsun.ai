import type { Metadata, Viewport } from 'next';
import type { ReactNode } from 'react';
import { ServiceWorkerRegistration } from '@/components/ServiceWorkerRegistration';
import './globals.css';

export const metadata: Metadata = {
  title: '智慧長照 AI 陪伴系統',
  description: '語音優先的長者 AI 陪伴系統',
  manifest: '/manifest.json',
};

/* §7.4 — must NOT restrict zoom. `maximumScale` is deliberately absent:
   capping it blocks pinch-zoom, which is the same accessibility failure as
   user-scalable=no and is disallowed for a 75+ audience. */
export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#0891B2',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-Hant-TW">
      <body>
        {children}
        <ServiceWorkerRegistration />
      </body>
    </html>
  );
}
