import { cookies } from 'next/headers';
import type { ReactNode } from 'react';
import { PublicShell } from '@/components/public/PublicShell';
import { LOCALE_COOKIE, parseLocaleCookie } from '@/lib/i18n/locale-cookie';
import { accessTokenCookieName } from '@/lib/server/auth-cookie';

/**
 * Shared public shell for legal/information pages. Cookie presence only chooses
 * the header affordance; it is never treated as authorization for protected
 * data (the Core remains authoritative on every read).
 */
export default async function PublicLayout({ children }: { children: ReactNode }) {
  const cookieStore = await cookies();
  const initialLocale = parseLocaleCookie(cookieStore.get(LOCALE_COOKIE)?.value);
  const signedIn = Boolean(cookieStore.get(accessTokenCookieName())?.value);

  return (
    <PublicShell initialLocale={initialLocale} signedIn={signedIn}>
      {children}
    </PublicShell>
  );
}
