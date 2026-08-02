'use client';

import { StateCard } from '@/components/StateCard';
import type { MemoryView } from '@/lib/api/memories';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';

export interface MemoryListProps {
  candidates: MemoryView[];
  confirmed: MemoryView[];
  onReject: (memory: MemoryView) => Promise<void>;
  onDelete: (memory: MemoryView) => Promise<void>;
}

export function MemoryList({
  candidates,
  confirmed,
  onReject,
  onDelete,
}: MemoryListProps) {
  const { t, formatDateTime } = useLocale();

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--block-gap)' }}>
      <section>
        <h3
          style={{
            fontSize: 'var(--text-lg)',
            marginBottom: 'var(--space-2)',
            color: 'var(--color-foreground)',
          }}
        >
          {t('memory.candidatesTitle', { count: candidates.length })}
        </h3>
        {candidates.length === 0 && (
          <p style={{ color: 'var(--color-muted-foreground)' }}>{t('memory.candidatesEmpty')}</p>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          {candidates.map((memory) => (
            /* Dashed outline — §4.2. An unconfirmed memory must never be drawn
               on a solid card, because the reviewer reads shape before text. */
            <StateCard
              key={memory.memoryId}
              state="candidate"
              title={t(`memoryType.${memory.memoryType}` as MessageKey)}
              meta={t('memory.sourceEvents', {
                count: memory.sourceEventIds.length,
                version: memory.version,
              })}
              actions={
                <button type="button" onClick={() => onReject(memory)}>
                  {t('memory.reject')}
                </button>
              }
            >
              {memory.content}
            </StateCard>
          ))}
        </div>
      </section>

      <section>
        <h3
          style={{
            fontSize: 'var(--text-lg)',
            marginBottom: 'var(--space-2)',
            color: 'var(--color-foreground)',
          }}
        >
          {t('memory.confirmedTitle', { count: confirmed.length })}
        </h3>
        {confirmed.length === 0 && (
          <p style={{ color: 'var(--color-muted-foreground)' }}>{t('memory.confirmedEmpty')}</p>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          {confirmed.map((memory) => (
            <StateCard
              key={memory.memoryId}
              state="confirmed"
              title={t(`memoryType.${memory.memoryType}` as MessageKey)}
              meta={t('memory.confirmedMeta', {
                by: memory.confirmedBy ?? t('common.empty'),
                at: formatDateTime(memory.confirmedAt),
              })}
              actions={
                <button type="button" onClick={() => onDelete(memory)}>
                  {t('memory.delete')}
                </button>
              }
            >
              {memory.content}
            </StateCard>
          ))}
        </div>
      </section>
    </div>
  );
}
