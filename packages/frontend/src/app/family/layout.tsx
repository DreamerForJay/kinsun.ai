import type { ReactNode } from 'react';
import { SurfaceShell } from '@/components/SurfaceShell';
import { LOCALE_COOKIE, parseLocaleCookie } from '@/lib/i18n/locale-cookie';
import { cookies } from 'next/headers';

export default function FamilyLayout({ children }: { children: ReactNode }) {
  const locale = parseLocaleCookie(cookies().get(LOCALE_COOKIE)?.value);
  return (
    <SurfaceShell surface="family" initialLocale={locale}>
      {children}
    </SurfaceShell>
  );
}
