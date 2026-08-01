'use client';

import type { ReactNode } from 'react';
import { LanguageSwitch } from '@/components/LanguageSwitch';
import { LocaleProvider, useLocale } from '@/lib/i18n/locale-context';
import { localeTag, type Locale } from '@/lib/i18n/messages';
import styles from './SurfaceShell.module.css';

export interface SurfaceShellProps {
  /** Selects the token overrides in `app/tokens.css`. The voice surface does not
   *  use this shell — it sets `data-surface` itself and has no language switch. */
  surface: 'care' | 'family';
  initialLocale: Locale;
  children: ReactNode;
}

export function SurfaceShell({ surface, initialLocale, children }: SurfaceShellProps) {
  return (
    <LocaleProvider initialLocale={initialLocale}>
      <SurfaceFrame surface={surface}>{children}</SurfaceFrame>
    </LocaleProvider>
  );
}

function SurfaceFrame({ surface, children }: { surface: 'care' | 'family'; children: ReactNode }) {
  const { locale } = useLocale();

  return (
    // `lang` is set here rather than on <html>: the root layout is shared with
    // the Chinese-only voice surface, so the switch must scope to this subtree.
    <div className={styles.shell} data-surface={surface} lang={localeTag(locale)}>
      <header className={styles.header}>
        <LanguageSwitch />
      </header>
      {children}
    </div>
  );
}
