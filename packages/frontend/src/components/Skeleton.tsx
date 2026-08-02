'use client';

import { useLocale } from '@/lib/i18n/locale-context';
import styles from './Skeleton.module.css';

export interface SkeletonProps {
  /** Roughly how many rows the real content will occupy. */
  rows?: number;
}

/**
 * Loading placeholder for the care and family surfaces (MASTER.md §10.2).
 *
 * The half of §10.2 that is easy to miss is the second clause: a reload must not
 * leave the previous result on screen looking complete. Callers therefore render
 * this *instead of* stale rows while refetching, not beside them — on a care
 * dashboard, data that silently belongs to a previous elder or a previous shift
 * is worse than a visibly empty panel.
 */
export function Skeleton({ rows = 3 }: SkeletonProps) {
  const { t } = useLocale();

  return (
    <div className={styles.list} role="status" aria-busy="true">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className={styles.bar} aria-hidden="true" />
      ))}
      <span className={styles.srOnly}>{t('common.loading')}</span>
    </div>
  );
}
