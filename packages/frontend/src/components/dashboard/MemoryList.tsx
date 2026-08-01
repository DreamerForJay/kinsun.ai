'use client';

import type { CoreMemoryType, MemoryView } from '@/lib/api/memories';

const MEMORY_TYPE_LABEL: Record<CoreMemoryType, string> = {
  PREFERENCE: '偏好',
  IMPORTANT_RELATIONSHIP: '重要關係',
  ROUTINE: '日常習慣',
  COMMUNICATION_PREFERENCE: '溝通偏好',
  PERSONAL_HISTORY: '個人經歷',
};

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
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <section>
        <h3 style={{ fontSize: 18, marginBottom: 8 }}>待確認候選記憶（{candidates.length}）</h3>
        {candidates.length === 0 && <p style={{ color: '#718096' }}>目前沒有待確認的候選記憶。</p>}
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
              <strong>[{MEMORY_TYPE_LABEL[memory.memoryType]}]</strong> {memory.content}
              <div style={{ fontSize: 12, color: '#718096' }}>
                來源事件 {memory.sourceEventIds.length} 筆｜版本 {memory.version}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="button" onClick={() => onConfirm(memory)}>
                確認
              </button>
              <button type="button" onClick={() => onReject(memory)}>
                拒絕
              </button>
            </div>
          </div>
        ))}
      </section>

      <section>
        <h3 style={{ fontSize: 18, marginBottom: 8 }}>有效記憶（{confirmed.length}）</h3>
        {confirmed.length === 0 && <p style={{ color: '#718096' }}>目前沒有有效記憶。</p>}
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
              <strong>[{MEMORY_TYPE_LABEL[memory.memoryType]}]</strong> {memory.content}
              <div style={{ fontSize: 12, color: '#718096' }}>
                確認者：{memory.confirmedBy ?? '—'}｜確認時間：
                {memory.confirmedAt ? new Date(memory.confirmedAt).toLocaleString('zh-TW') : '—'}
              </div>
            </div>
            <button type="button" onClick={() => onDelete(memory)}>
              刪除
            </button>
          </div>
        ))}
      </section>
    </div>
  );
}
