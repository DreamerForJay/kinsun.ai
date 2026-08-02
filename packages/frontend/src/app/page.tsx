import { cookies } from 'next/headers';
import { Landing } from '@/components/landing/Landing';
import { PublicShell } from '@/components/public/PublicShell';
import { VoiceHomeClient } from '@/components/voice/VoiceHomeClient';
import { LOCALE_COOKIE, parseLocaleCookie } from '@/lib/i18n/locale-cookie';
import { accessTokenCookieName } from '@/lib/server/auth-cookie';

/**
 * Forks on session-cookie presence only — never an authorization signal, Core
 * re-authorizes every read regardless (AGENTS.md §5; same contract as
 * `SurfaceShell`'s `signedIn` prop). A signed-in visitor goes straight into
 * the existing voice companion; everyone else gets the public landing page
 * instead of the bare "尚未設定本機 Demo 身分" message that used to be the
 * very first thing anyone — including a hackathon judge following the
 * README's Live Demo link — saw here.
 */
export default async function HomePage() {
  const cookieStore = await cookies();
  const signedIn = Boolean(cookieStore.get(accessTokenCookieName())?.value);

  if (signedIn) {
    return <VoiceHomeClient />;
  }

  const locale = parseLocaleCookie(cookieStore.get(LOCALE_COOKIE)?.value);
  return (
    <PublicShell initialLocale={locale} signedIn={false}>
      <Landing />
    </PublicShell>
  );
}
