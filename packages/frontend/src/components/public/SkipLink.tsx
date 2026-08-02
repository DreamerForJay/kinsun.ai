'use client';

import { useLocale } from '@/lib/i18n/locale-context';
import styles from './SkipLink.module.css';

/**
 * First focusable element on the public surface. Off-screen until focused, so
 * it costs sighted mouse users nothing but gives keyboard/screen-reader users
 * a way past the header nav without tabbing through every link (ux skill §1
 * `skip-links`) — nothing on this surface had one before.
 */
export function SkipLink() {
  const { t } = useLocale();
  return (
    <a href="#main-content" className={styles.link}>
      {t('a11y.skipToContent')}
    </a>
  );
}
