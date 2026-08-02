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
  /* The one place a literal colour is correct rather than merely tolerated:
     this becomes <meta name="theme-color">, which the browser's own chrome
     reads before any stylesheet is applied, so a CSS variable cannot resolve
     here. Keep the value equal to --color-primary (cyan-600) in tokens.css. */
  // eslint-disable-next-line no-restricted-syntax -- theme-color meta cannot use a CSS variable (MASTER.md §14)
  themeColor: '#0891B2',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    /* The default surface is `voice`, not `care`.
       tokens.css's :root values happen to equal the care scale, which meant any
       page that forgot to declare a surface silently rendered at 16px — the
       smallest scale, on a product whose primary user is 75+. MASTER.md §5.1
       calls 22px a floor, not a preference, so the safe failure mode is the
       elder scale. The care and family surfaces override this explicitly in
       SurfaceShell; nothing renders at the elder scale by accident. */
    <html lang="zh-Hant-TW">
      <body data-surface="voice">
        {children}
        <ServiceWorkerRegistration />
      </body>
    </html>
  );
}
