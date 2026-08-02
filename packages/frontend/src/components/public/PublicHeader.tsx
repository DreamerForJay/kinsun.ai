'use client';

import { useState } from 'react';
import Link from 'next/link';
import { List, X } from '@phosphor-icons/react';
import { LanguageSwitch } from '@/components/LanguageSwitch';
import { SignOutButton } from '@/components/SignOutButton';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import styles from './PublicHeader.module.css';

export interface PublicHeaderProps {
  /** Whether a session cookie is present. Only controls which CTA is shown —
   *  never an authorization signal (same contract as SurfaceShell's prop). */
  signedIn: boolean;
}

const NAV_ITEMS: ReadonlyArray<{ href: string; key: MessageKey }> = [
  { href: '/', key: 'public.nav.about' },
  { href: '/privacy', key: 'public.nav.privacy' },
  { href: '/accessibility', key: 'public.nav.accessibility' },
];

/**
 * Sticky header for the public surface (MASTER.md §7.3). Collapses to a
 * disclosure below 768px — the toggle is icon + text, never icon-only (§8.4,
 * §14), and the panel it controls is announced via `aria-expanded`/`aria-controls`.
 */
export function PublicHeader({ signedIn }: PublicHeaderProps) {
  const { t } = useLocale();
  const [open, setOpen] = useState(false);

  return (
    <header className={styles.header}>
      <div className={styles.bar}>
        <Link href="/" className={styles.brand} aria-label={t('public.header.brand')}>
          <span className={styles.brandFull} aria-hidden="true">
            {t('public.header.brand')}
          </span>
          <span className={styles.brandCompact} aria-hidden="true">
            {t('public.header.brandCompact')}
          </span>
        </Link>

        <button
          type="button"
          className={styles.menuToggle}
          aria-expanded={open}
          aria-controls="public-nav-panel"
          onClick={() => setOpen((current) => !current)}
        >
          {open ? (
            <X size={24} weight="bold" aria-hidden="true" />
          ) : (
            <List size={24} weight="bold" aria-hidden="true" />
          )}
          <span>{open ? t('public.nav.close') : t('public.nav.menu')}</span>
        </button>

        <div id="public-nav-panel" className={styles.panel} data-open={open}>
          <nav aria-label={t('public.nav.primaryLabel')} className={styles.nav}>
            {NAV_ITEMS.map((item) => (
              <Link key={item.href} href={item.href} className={styles.navLink}>
                {t(item.key)}
              </Link>
            ))}
          </nav>

          <div className={styles.actions}>
            <LanguageSwitch compactLabel />
            <div className={styles.authAction}>
              {signedIn ? (
                <SignOutButton label={t('common.signOut')} />
              ) : (
                <Link href="/sign-in" className={styles.signIn}>
                  {t('public.cta.signIn')}
                </Link>
              )}
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
