import type { ReactNode } from 'react';
import { SurfaceShell } from '@/components/SurfaceShell';
import { LOCALE_COOKIE, parseLocaleCookie } from '@/lib/i18n/locale-cookie';
import { cookies } from 'next/headers';

/* Staff sign-in is a care-surface entry point, so it uses the care token scale
   and offers the same language choice the dashboard does. */
export default async function StaffLayout({ children }: { children: ReactNode }) {
  const cookieStore = await cookies();
  const locale = parseLocaleCookie(cookieStore.get(LOCALE_COOKIE)?.value);
  return (
    <SurfaceShell surface="care" initialLocale={locale}>
      {children}
    </SurfaceShell>
  );
}
