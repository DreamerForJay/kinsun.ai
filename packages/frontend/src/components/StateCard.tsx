'use client';

import {
  CheckCircle,
  CircleDashed,
  Minus,
  PaperPlaneTilt,
  Prohibit,
  Warning,
  type Icon,
} from '@phosphor-icons/react';
import type { ReactNode } from 'react';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import styles from './StateCard.module.css';

/**
 * The six workflow states MASTER.md §4.2 defines, and the only vocabulary the
 * care and family surfaces may use to show "how settled is this record".
 *
 * §2 is the constraint that matters: these express workflow state, never the
 * elder's health. Green means "this has been reviewed", not "she is doing well".
 */
export type WorkflowState =
  'candidate' | 'needsReview' | 'confirmed' | 'published' | 'withdrawn' | 'dataInsufficient';

const STATE_ICON: Record<WorkflowState, Icon> = {
  candidate: CircleDashed,
  needsReview: Warning,
  confirmed: CheckCircle,
  published: PaperPlaneTilt,
  withdrawn: Prohibit,
  dataInsufficient: Minus,
};

const STATE_LABEL: Record<WorkflowState, MessageKey> = {
  candidate: 'state.candidate',
  needsReview: 'state.needsReview',
  confirmed: 'state.confirmed',
  published: 'state.published',
  withdrawn: 'state.withdrawn',
  dataInsufficient: 'state.dataInsufficient',
};

/* ---- domain enum -> workflow state ----------------------------------------
 * Kept here rather than at each call site so one state cannot end up drawn two
 * different ways on two screens (§4.2 requires the same state to read the same
 * everywhere). Exported so the mapping itself is testable.
 */

export function careEventState(status: string): WorkflowState {
  switch (status) {
    case 'CANDIDATE':
      return 'candidate';
    case 'NEEDS_REVIEW':
      return 'needsReview';
    case 'VERIFIED':
    case 'CORRECTED':
      return 'confirmed';
    // Rejected and excluded are terminal negatives: the record stands, its
    // content does not. That is the withdrawn shape, struck-through title
    // included.
    case 'REJECTED':
    case 'EXCLUDED':
      return 'withdrawn';
    default:
      // An unknown status must not render as settled. Falling back to
      // `candidate` keeps the dashed outline, which is the safe reading.
      return 'candidate';
  }
}

export function summaryState(status: string): WorkflowState {
  switch (status) {
    case 'DRAFT':
      return 'candidate';
    case 'READY':
    case 'NEEDS_REVIEW':
      return 'needsReview';
    case 'PUBLISHED':
      return 'published';
    case 'WITHDRAWN':
      return 'withdrawn';
    case 'STALE':
      return 'dataInsufficient';
    default:
      return 'candidate';
  }
}

export function familyReportState(status: string): WorkflowState {
  switch (status) {
    case 'PUBLISHED':
      return 'published';
    case 'WITHDRAWN':
      return 'withdrawn';
    // DRAFT / NEEDS_REVIEW / STALE are filtered out before they reach the family
    // surface (lib/api/family-guard.ts). If one ever arrives anyway, it must not
    // be drawn as a published fact.
    default:
      return 'candidate';
  }
}

/** Icon size per surface, MASTER.md §8.4. Care is the denser of the two. */
const ICON_SIZE = 20;

export interface StateBadgeProps {
  state: WorkflowState;
  /**
   * Overrides the generic state word with the precise domain label.
   *
   * Several domain values share one shape — VERIFIED and CORRECTED are both
   * `confirmed`, REJECTED and EXCLUDED are both `withdrawn`. The shape is what
   * §4.2 standardises; collapsing the wording too would cost a reviewer the
   * distinction between an event they verified and one they had to correct.
   */
  label?: ReactNode;
}

/**
 * Colour + icon + text together, always (§4.2 / §13). Used on its own inside
 * the event table, where a full card would not fit a table cell.
 */
export function StateBadge({ state, label }: StateBadgeProps) {
  const { t } = useLocale();
  const IconComponent = STATE_ICON[state];

  return (
    <span className={styles.badge} data-state={state}>
      <IconComponent size={ICON_SIZE} weight="bold" aria-hidden="true" />
      {label ?? t(STATE_LABEL[state])}
    </span>
  );
}

export interface StateCardProps {
  state: WorkflowState;
  title?: ReactNode;
  /** Secondary line — version, source counts, timestamps. */
  meta?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
}

export function StateCard({ state, title, meta, actions, children }: StateCardProps) {
  return (
    <section className={styles.card} data-state={state}>
      <div className={styles.header}>
        <span className={styles.title}>{title}</span>
        <StateBadge state={state} />
      </div>
      <div className={styles.body}>{children}</div>
      {meta && <div className={styles.meta}>{meta}</div>}
      {actions && <div className={styles.actions}>{actions}</div>}
    </section>
  );
}
