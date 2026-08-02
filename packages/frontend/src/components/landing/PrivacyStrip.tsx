'use client';

import Link from 'next/link';
import { ArrowCounterClockwise, Eye, LockKey, ShieldCheck, type Icon } from '@phosphor-icons/react';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import styles from './PrivacyStrip.module.css';

const POINTS: ReadonlyArray<{ icon: Icon; key: MessageKey }> = [
  { icon: ShieldCheck, key: 'landing.privacy.point1' },
  { icon: LockKey, key: 'landing.privacy.point2' },
  { icon: Eye, key: 'landing.privacy.point3' },
  { icon: ArrowCounterClockwise, key: 'landing.privacy.point4' },
];

export function PrivacyStrip() {
  const { t } = useLocale();

  return (
    <section className={styles.section} aria-labelledby="privacy-heading">
      <h2 id="privacy-heading" className={styles.title}>
        {t('landing.privacy.title')}
      </h2>
      <p className={styles.subtitle}>{t('landing.privacy.subtitle')}</p>

      <ul className={styles.list}>
        {POINTS.map((point) => {
          const PointIcon = point.icon;
          return (
            <li key={point.key} className={styles.item}>
              <PointIcon size={24} weight="bold" aria-hidden="true" className={styles.icon} />
              <span>{t(point.key)}</span>
            </li>
          );
        })}
      </ul>

      <Link href="/privacy" className={styles.cta}>
        {t('landing.privacy.cta')}
      </Link>
    </section>
  );
}
