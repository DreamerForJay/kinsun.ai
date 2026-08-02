'use client';

import { Prohibit } from '@phosphor-icons/react';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import styles from './BoundaryList.module.css';

const ITEMS: readonly MessageKey[] = [
  'landing.boundaries.item1',
  'landing.boundaries.item2',
  'landing.boundaries.item3',
  'landing.boundaries.item4',
  'landing.boundaries.item5',
];

/** Mirrors the "明確禁止" list in docs/demo/ui/index.html — same content
 *  source (AGENTS.md §4), same red-prohibition-icon convention. */
export function BoundaryList() {
  const { t } = useLocale();

  return (
    <section className={styles.section} aria-labelledby="boundaries-heading">
      <h2 id="boundaries-heading" className={styles.title}>
        {t('landing.boundaries.title')}
      </h2>
      <p className={styles.subtitle}>{t('landing.boundaries.subtitle')}</p>

      <ul className={styles.list}>
        {ITEMS.map((key) => (
          <li key={key} className={styles.item}>
            <Prohibit size={22} weight="bold" aria-hidden="true" className={styles.icon} />
            <span>{t(key)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
