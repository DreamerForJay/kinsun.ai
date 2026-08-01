'use client';

import type { MemoryView } from '@/lib/api/memories';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';

export interface MemoryListProps {
  candidates: MemoryView[];
  confirmed: MemoryView[];
  onConfirm: (memory: MemoryView) => Promise<void>;
  onReject: (memory: MemoryView) => Promise<void>;
  onDelete: (memory: MemoryView) => Promise<void>;
}

export function MemoryList({
  candidates,
  confirmed,
  onConfirm,
  onReject,
  onDelete,
}: MemoryListProps) {
  const { t, formatDateTime } = useLocale();

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <section>
        <h3 style={{ fontSize: 18, marginBottom: 8 }}>
          {t('memory.candidatesTitle', { count: candidates.length })}
        </h3>
        {candidates.length === 0 && (
          <p style={{ color: '#718096' }}>{t('memory.candidatesEmpty')}</p>
        )}
        {candidates.map((memory) => (
          <div
            key={memory.memoryId}
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: 10,
              border: '1px solid #e2e8f0',
              borderRadius: 8,
              marginBottom: 8,
            }}
          >
            <div>
              <strong>[{t(`memoryType.${memory.memoryType}` as MessageKey)}]</strong>{' '}
              {memory.content}
              <div style={{ fontSize: 12, color: '#718096' }}>
                {t('memory.sourceEvents', {
                  count: memory.sourceEventIds.length,
                  version: memory.version,
                })}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="button" onClick={() => onConfirm(memory)}>
                {t('memory.confirm')}
              </button>
              <button type="button" onClick={() => onReject(memory)}>
                {t('memory.reject')}
              </button>
            </div>
          </div>
        ))}
      </section>

      <section>
        <h3 style={{ fontSize: 18, marginBottom: 8 }}>
          {t('memory.confirmedTitle', { count: confirmed.length })}
        </h3>
        {confirmed.length === 0 && <p style={{ color: '#718096' }}>{t('memory.confirmedEmpty')}</p>}
        {confirmed.map((memory) => (
          <div
            key={memory.memoryId}
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: 10,
              border: '1px solid #e2e8f0',
              borderRadius: 8,
              marginBottom: 8,
            }}
          >
            <div>
              <strong>[{t(`memoryType.${memory.memoryType}` as MessageKey)}]</strong>{' '}
              {memory.content}
              <div style={{ fontSize: 12, color: '#718096' }}>
                {t('memory.confirmedMeta', {
                  by: memory.confirmedBy ?? t('common.empty'),
                  at: formatDateTime(memory.confirmedAt),
                })}
              </div>
            </div>
            <button type="button" onClick={() => onDelete(memory)}>
              {t('memory.delete')}
            </button>
          </div>
        ))}
      </section>
    </div>
  );
}
