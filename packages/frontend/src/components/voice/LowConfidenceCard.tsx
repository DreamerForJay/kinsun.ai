'use client';

import { useEffect, useRef } from 'react';
import { ArrowClockwise, CheckCircle, Clock } from '@phosphor-icons/react';
import styles from './LowConfidenceCard.module.css';

export interface LowConfidenceCardProps {
  transcript: string;
  onConfirm: () => void;
  onRetry: () => void;
  onDefer: () => void;
}

/**
 * Low Confidence state (design-system/MASTER.md §10.1): a full-screen card that
 * asks 我聽到「…」，是這樣嗎？ before anything is treated as understood.
 * This is the Gate 1 rule that ASR must not pretend to have recognised
 * correctly (AGENTS.md §3 item 2) — so the elder gets three ways out, not two
 * (§1 可復原).
 */
export function LowConfidenceCard({ transcript, onConfirm, onRetry, onDefer }: LowConfidenceCardProps) {
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    confirmRef.current?.focus();
  }, []);

  return (
    <div className={styles.overlay} role="dialog" aria-modal="true" aria-labelledby="low-confidence-question">
      <div className={styles.card}>
        {/* role="alert" so the question is announced the moment it appears (§13). */}
        <div role="alert">
          <p id="low-confidence-question" className={styles.question}>
            我聽到「…」，是這樣嗎？
          </p>
          <p className={styles.transcript}>「{transcript}」</p>
        </div>

        <div className={styles.actions}>
          <button
            ref={confirmRef}
            type="button"
            onClick={onConfirm}
            className={`${styles.action} ${styles.confirm}`}
          >
            <CheckCircle size={40} weight="fill" aria-hidden="true" />
            <span>對，就是這樣</span>
          </button>

          <button type="button" onClick={onRetry} className={`${styles.action} ${styles.secondary}`}>
            <ArrowClockwise size={40} weight="fill" aria-hidden="true" />
            <span>不對，我再說一次</span>
          </button>

          <button type="button" onClick={onDefer} className={`${styles.action} ${styles.ghost}`}>
            <Clock size={40} weight="fill" aria-hidden="true" />
            <span>稍後再說</span>
          </button>
        </div>
      </div>
    </div>
  );
}
