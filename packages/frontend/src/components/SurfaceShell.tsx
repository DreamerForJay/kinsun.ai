'use client';

import type { ReactNode } from 'react';
import { LanguageSwitch } from '@/components/LanguageSwitch';
import { SignOutButton } from '@/components/SignOutButton';
import { LocaleProvider, useLocale } from '@/lib/i18n/locale-context';
import { localeTag, type Locale } from '@/lib/i18n/messages';
import styles from './SurfaceShell.module.css';

export interface SurfaceShellProps {
  /** Selects the token overrides in `app/tokens.css`. The voice surface does not
   *  use this shell — it sets `data-surface` itself and has no language switch. */
  surface: 'care' | 'family';
  initialLocale: Locale;
  /**
   * Whether a session cookie is present, decided by the (server) layout.
   *
   * Only controls whether a sign-out affordance is offered — it is not an
   * authorization signal and must never gate content. The cookie's presence says
   * nothing about its validity; Core re-authorizes every read regardless
   * (AGENTS.md §5). Without it the shell would offer "sign out" on the sign-in
   * pages, which also live on these surfaces.
   */
  signedIn: boolean;
  children: ReactNode;
}

export function SurfaceShell({ surface, initialLocale, signedIn, children }: SurfaceShellProps) {
  return (
    <LocaleProvider initialLocale={initialLocale}>
      <SurfaceFrame surface={surface} signedIn={signedIn}>
        {children}
      </SurfaceFrame>
    </LocaleProvider>
  );
}

function SurfaceFrame({
  surface,
  signedIn,
  children,
}: {
  surface: 'care' | 'family';
  signedIn: boolean;
  children: ReactNode;
}) {
  const { locale, t } = useLocale();

  return (
    // `lang` is set here rather than on <html>: the root layout is shared with
    // the Chinese-only voice surface, so the switch must scope to this subtree.
    <div className={styles.shell} data-surface={surface} lang={localeTag(locale)}>
      <header className={styles.header}>
        <LanguageSwitch />
        {signedIn && <SignOutButton label={t('common.signOut')} />}
      </header>
      {children}
    </div>
  );
}
