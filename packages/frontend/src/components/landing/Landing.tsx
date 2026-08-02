'use client';

import Link from 'next/link';
import { useLocale } from '@/lib/i18n/locale-context';
import { BoundaryList } from './BoundaryList';
import { Hero } from './Hero';
import { ModuleCards } from './ModuleCards';
import styles from './Landing.module.css';
import { PrivacyStrip } from './PrivacyStrip';
import { RoleCards } from './RoleCards';

/**
 * Signed-out `/`. The closing CTA is a plain link, not a filled button —
 * Hero already owns this page's one filled action (MASTER.md §8.1).
 */
export function Landing() {
  const { t } = useLocale();

  return (
    <>
      <Hero />
      <ModuleCards />
      <RoleCards />
      <PrivacyStrip />
      <BoundaryList />

      <section className={styles.closing} aria-labelledby="closing-heading">
        <h2 id="closing-heading" className={styles.closingTitle}>
          {t('landing.closing.title')}
        </h2>
        <p className={styles.closingBody}>{t('landing.closing.body')}</p>
        <Link href="/sign-in" className={styles.closingCta}>
          {t('landing.closing.cta')}
        </Link>
      </section>
    </>
  );
}
