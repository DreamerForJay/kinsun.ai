'use client';

import Link from 'next/link';
import { FirstAidKit, User, UsersThree, type Icon } from '@phosphor-icons/react';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import styles from './RoleCards.module.css';

interface RoleItem {
  href: string;
  icon: Icon;
  titleKey: MessageKey;
  bodyKey: MessageKey;
  ctaKey: MessageKey;
}

/** Deep-links straight into each role's existing entry point, skipping
 *  `/sign-in` — that page remains reachable on its own (e.g. from a signed-out
 *  redirect), this just gives the landing page its own way in. */
const ROLES: readonly RoleItem[] = [
  {
    href: '/elder/start',
    icon: User,
    titleKey: 'landing.roles.elder.title',
    bodyKey: 'landing.roles.elder.body',
    ctaKey: 'landing.roles.elder.cta',
  },
  {
    href: '/family/join',
    icon: UsersThree,
    titleKey: 'landing.roles.family.title',
    bodyKey: 'landing.roles.family.body',
    ctaKey: 'landing.roles.family.cta',
  },
  {
    href: '/staff/sign-in',
    icon: FirstAidKit,
    titleKey: 'landing.roles.staff.title',
    bodyKey: 'landing.roles.staff.body',
    ctaKey: 'landing.roles.staff.cta',
  },
];

export function RoleCards() {
  const { t } = useLocale();

  return (
    <section className={styles.section} aria-labelledby="roles-heading">
      <h2 id="roles-heading" className={styles.title}>
        {t('landing.roles.title')}
      </h2>
      <p className={styles.subtitle}>{t('landing.roles.subtitle')}</p>

      <div className={styles.grid}>
        {ROLES.map((role) => {
          const RoleIcon = role.icon;
          return (
            <Link key={role.href} href={role.href} className={styles.card}>
              <RoleIcon size={32} weight="fill" aria-hidden="true" className={styles.icon} />
              <h3 className={styles.cardTitle}>{t(role.titleKey)}</h3>
              <p className={styles.cardBody}>{t(role.bodyKey)}</p>
              <span className={styles.cta}>{t(role.ctaKey)} →</span>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
