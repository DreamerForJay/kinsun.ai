'use client';

import Link from 'next/link';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import styles from './PublicFooter.module.css';

const LEGAL_LINKS: ReadonlyArray<{ href: string; key: MessageKey }> = [
  { href: '/privacy', key: 'public.nav.privacy' },
  { href: '/terms', key: 'public.nav.terms' },
  { href: '/data-rights', key: 'public.nav.dataRights' },
  { href: '/accessibility', key: 'public.nav.accessibility' },
];

export function PublicFooter() {
  const { t } = useLocale();

  return (
    <footer className={styles.footer}>
      <nav aria-label={t('public.nav.footerLabel')} className={styles.links}>
        {LEGAL_LINKS.map((item) => (
          <Link key={item.href} href={item.href} className={styles.link}>
            {t(item.key)}
          </Link>
        ))}
      </nav>
      {/* AGENTS.md §4 — demo/test material must be disclosed as synthetic. */}
      <p className={styles.note}>{t('public.footer.demoNotice')}</p>
    </footer>
  );
}
