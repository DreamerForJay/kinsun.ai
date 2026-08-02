'use client';

import Link from 'next/link';
import { useLocale } from '@/lib/i18n/locale-context';
import styles from './Hero.module.css';

/**
 * The only filled primary button on this page lives here (MASTER.md §8.1:
 * one filled action per screen). Everything else on the landing page —
 * including the closing CTA — stays outline or plain-link.
 */
export function Hero() {
  const { t } = useLocale();

  return (
    <section className={styles.hero}>
      {/* Decorative: the brand name right below already says the same thing. */}
      <img src="/mascot.png" alt="" width={160} height={160} className={styles.mascot} />
      <h1 className={styles.title}>{t('landing.hero.title')}</h1>
      <p className={styles.subtitle}>{t('landing.hero.subtitle')}</p>
      <div className={styles.actions}>
        <Link href="/sign-in" className={styles.primary}>
          {t('landing.hero.ctaPrimary')}
        </Link>
        <Link href="/privacy" className={styles.secondary}>
          {t('landing.hero.ctaSecondary')}
        </Link>
      </div>
    </section>
  );
}
