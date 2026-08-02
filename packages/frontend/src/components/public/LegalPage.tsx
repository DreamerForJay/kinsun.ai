'use client';

import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import styles from './LegalPage.module.css';

export const LEGAL_PAGE_IDS = ['privacy', 'terms', 'dataRights', 'accessibility'] as const;
export type LegalPageId = (typeof LEGAL_PAGE_IDS)[number];

interface LegalSectionDefinition {
  titleKey: MessageKey;
  paragraphKeys: readonly MessageKey[];
  itemKeys?: readonly MessageKey[];
}

interface LegalPageDefinition {
  titleKey: MessageKey;
  introKey: MessageKey;
  noticeKey: MessageKey;
  sections: readonly LegalSectionDefinition[];
}

const LEGAL_PAGES: Record<LegalPageId, LegalPageDefinition> = {
  privacy: {
    titleKey: 'legal.privacy.title',
    introKey: 'legal.privacy.intro',
    noticeKey: 'legal.privacy.notice',
    sections: [
      {
        titleKey: 'legal.privacy.scope.title',
        paragraphKeys: ['legal.privacy.scope.body'],
        itemKeys: [
          'legal.privacy.scope.item1',
          'legal.privacy.scope.item2',
          'legal.privacy.scope.item3',
          'legal.privacy.scope.item4',
        ],
      },
      {
        titleKey: 'legal.privacy.purpose.title',
        paragraphKeys: ['legal.privacy.purpose.body'],
        itemKeys: [
          'legal.privacy.purpose.item1',
          'legal.privacy.purpose.item2',
          'legal.privacy.purpose.item3',
        ],
      },
      {
        titleKey: 'legal.privacy.access.title',
        paragraphKeys: ['legal.privacy.access.body'],
        itemKeys: [
          'legal.privacy.access.item1',
          'legal.privacy.access.item2',
          'legal.privacy.access.item3',
          'legal.privacy.access.item4',
        ],
      },
      {
        titleKey: 'legal.privacy.ai.title',
        paragraphKeys: ['legal.privacy.ai.body'],
      },
      {
        titleKey: 'legal.privacy.retention.title',
        paragraphKeys: ['legal.privacy.retention.body1', 'legal.privacy.retention.body2'],
      },
      {
        titleKey: 'legal.privacy.contact.title',
        paragraphKeys: ['legal.privacy.contact.body'],
      },
    ],
  },
  terms: {
    titleKey: 'legal.terms.title',
    introKey: 'legal.terms.intro',
    noticeKey: 'legal.terms.notice',
    sections: [
      {
        titleKey: 'legal.terms.scope.title',
        paragraphKeys: ['legal.terms.scope.body'],
      },
      {
        titleKey: 'legal.terms.accounts.title',
        paragraphKeys: ['legal.terms.accounts.body'],
        itemKeys: [
          'legal.terms.accounts.item1',
          'legal.terms.accounts.item2',
          'legal.terms.accounts.item3',
        ],
      },
      {
        titleKey: 'legal.terms.use.title',
        paragraphKeys: ['legal.terms.use.body'],
        itemKeys: [
          'legal.terms.use.item1',
          'legal.terms.use.item2',
          'legal.terms.use.item3',
          'legal.terms.use.item4',
        ],
      },
      {
        titleKey: 'legal.terms.safety.title',
        paragraphKeys: ['legal.terms.safety.body1', 'legal.terms.safety.body2'],
      },
      {
        titleKey: 'legal.terms.ai.title',
        paragraphKeys: ['legal.terms.ai.body'],
      },
      {
        titleKey: 'legal.terms.availability.title',
        paragraphKeys: ['legal.terms.availability.body1', 'legal.terms.availability.body2'],
      },
    ],
  },
  dataRights: {
    titleKey: 'legal.dataRights.title',
    introKey: 'legal.dataRights.intro',
    noticeKey: 'legal.dataRights.notice',
    sections: [
      {
        titleKey: 'legal.dataRights.rights.title',
        paragraphKeys: ['legal.dataRights.rights.body'],
        itemKeys: [
          'legal.dataRights.rights.item1',
          'legal.dataRights.rights.item2',
          'legal.dataRights.rights.item3',
          'legal.dataRights.rights.item4',
          'legal.dataRights.rights.item5',
        ],
      },
      {
        titleKey: 'legal.dataRights.controls.title',
        paragraphKeys: ['legal.dataRights.controls.body'],
        itemKeys: [
          'legal.dataRights.controls.item1',
          'legal.dataRights.controls.item2',
          'legal.dataRights.controls.item3',
        ],
      },
      {
        titleKey: 'legal.dataRights.request.title',
        paragraphKeys: ['legal.dataRights.request.body1', 'legal.dataRights.request.body2'],
      },
      {
        titleKey: 'legal.dataRights.withdrawal.title',
        paragraphKeys: ['legal.dataRights.withdrawal.body'],
        itemKeys: [
          'legal.dataRights.withdrawal.item1',
          'legal.dataRights.withdrawal.item2',
          'legal.dataRights.withdrawal.item3',
        ],
      },
      {
        titleKey: 'legal.dataRights.export.title',
        paragraphKeys: ['legal.dataRights.export.body'],
      },
      {
        titleKey: 'legal.dataRights.representative.title',
        paragraphKeys: ['legal.dataRights.representative.body'],
      },
    ],
  },
  accessibility: {
    titleKey: 'legal.accessibility.title',
    introKey: 'legal.accessibility.intro',
    noticeKey: 'legal.accessibility.notice',
    sections: [
      {
        titleKey: 'legal.accessibility.commitment.title',
        paragraphKeys: ['legal.accessibility.commitment.body'],
      },
      {
        titleKey: 'legal.accessibility.measures.title',
        paragraphKeys: ['legal.accessibility.measures.body'],
        itemKeys: [
          'legal.accessibility.measures.item1',
          'legal.accessibility.measures.item2',
          'legal.accessibility.measures.item3',
          'legal.accessibility.measures.item4',
          'legal.accessibility.measures.item5',
          'legal.accessibility.measures.item6',
        ],
      },
      {
        titleKey: 'legal.accessibility.status.title',
        paragraphKeys: ['legal.accessibility.status.body'],
      },
      {
        titleKey: 'legal.accessibility.limitations.title',
        paragraphKeys: ['legal.accessibility.limitations.body'],
        itemKeys: [
          'legal.accessibility.limitations.item1',
          'legal.accessibility.limitations.item2',
          'legal.accessibility.limitations.item3',
        ],
      },
      {
        titleKey: 'legal.accessibility.technology.title',
        paragraphKeys: ['legal.accessibility.technology.body'],
      },
      {
        titleKey: 'legal.accessibility.feedback.title',
        paragraphKeys: ['legal.accessibility.feedback.body1', 'legal.accessibility.feedback.body2'],
      },
    ],
  },
};

export function LegalPage({ page }: { page: LegalPageId }) {
  const { t } = useLocale();
  const definition = LEGAL_PAGES[page];
  const headingId = `legal-${page}-title`;

  return (
    <article className={styles.article} aria-labelledby={headingId} data-legal-document={page}>
      <header className={styles.header}>
        <p className={styles.kicker}>{t('legal.common.kicker')}</p>
        <h1 id={headingId} className={styles.title}>
          {t(definition.titleKey)}
        </h1>
        <p className={styles.intro}>{t(definition.introKey)}</p>
        <p className={styles.updated}>
          <time dateTime="2026-08-02">{t('legal.common.updated')}</time>
        </p>
      </header>

      <aside className={styles.notice} aria-label={t('legal.common.noticeTitle')}>
        <strong className={styles.noticeTitle}>{t('legal.common.noticeTitle')}</strong>
        <p className={styles.noticeBody}>{t(definition.noticeKey)}</p>
      </aside>

      {definition.sections.map((section) => (
        <section className={styles.section} key={section.titleKey}>
          <h2 className={styles.sectionTitle}>{t(section.titleKey)}</h2>
          {section.paragraphKeys.map((key) => (
            <p className={styles.paragraph} key={key}>
              {t(key)}
            </p>
          ))}
          {section.itemKeys && (
            <ul className={styles.list}>
              {section.itemKeys.map((key) => (
                <li key={key}>{t(key)}</li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </article>
  );
}
