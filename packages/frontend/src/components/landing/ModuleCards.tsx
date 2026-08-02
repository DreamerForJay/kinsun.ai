'use client';

import { CheckCircle, CircleDashed, Clock, type Icon } from '@phosphor-icons/react';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import styles from './ModuleCards.module.css';

type ModuleStatus = 'available' | 'partial' | 'planned';

interface ModuleItem {
  status: ModuleStatus;
  titleKey: MessageKey;
  bodyKey: MessageKey;
}

/**
 * Status reflects the actual current implementation, not the product plan —
 * AGENTS.md §1 forbids describing planned work as already done. Module C
 * (elder overview, event review, family reports) is genuinely wired end to
 * end; A and B are real but partial (text-only companion; candidate events
 * and read-only summaries, not full auto-extraction).
 */
const MODULES: readonly ModuleItem[] = [
  { status: 'partial', titleKey: 'landing.modules.a.title', bodyKey: 'landing.modules.a.body' },
  { status: 'partial', titleKey: 'landing.modules.b.title', bodyKey: 'landing.modules.b.body' },
  { status: 'available', titleKey: 'landing.modules.c.title', bodyKey: 'landing.modules.c.body' },
];

const STATUS_ICON: Record<ModuleStatus, Icon> = {
  available: CheckCircle,
  partial: CircleDashed,
  planned: Clock,
};

const STATUS_LABEL_KEY: Record<ModuleStatus, MessageKey> = {
  available: 'landing.modules.status.available',
  partial: 'landing.modules.status.partial',
  planned: 'landing.modules.status.planned',
};

const STATUS_CLASS: Record<ModuleStatus, string> = {
  available: styles.available,
  partial: styles.partial,
  planned: styles.planned,
};

export function ModuleCards() {
  const { t } = useLocale();

  return (
    <section className={styles.section} aria-labelledby="modules-heading">
      <h2 id="modules-heading" className={styles.title}>
        {t('landing.modules.title')}
      </h2>
      <p className={styles.subtitle}>{t('landing.modules.subtitle')}</p>

      <div className={styles.grid}>
        {MODULES.map((item) => {
          const StatusIcon = STATUS_ICON[item.status];
          return (
            <article key={item.titleKey} className={styles.card}>
              <h3 className={styles.cardTitle}>{t(item.titleKey)}</h3>
              {/* Status is icon + text together, never colour alone (§4.2). */}
              <span className={`${styles.status} ${STATUS_CLASS[item.status]}`}>
                <StatusIcon size={20} weight="bold" aria-hidden="true" />
                {t(STATUS_LABEL_KEY[item.status])}
              </span>
              <p className={styles.cardBody}>{t(item.bodyKey)}</p>
            </article>
          );
        })}
      </div>
    </section>
  );
}
