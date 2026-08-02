import { apiFetch, createIdempotencyKey, type ApiConfig } from './client';

export type CoreMemoryType =
  | 'PREFERENCE'
  | 'IMPORTANT_RELATIONSHIP'
  | 'ROUTINE'
  | 'COMMUNICATION_PREFERENCE'
  | 'PERSONAL_HISTORY';

export type CoreMemoryStatus =
  'CANDIDATE' | 'CONFIRMED' | 'ACTIVE' | 'DEFERRED' | 'REJECTED' | 'INACTIVE' | 'DELETED';

interface CoreMemory {
  memory_id: string;
  elder_id: string;
  memory_type: CoreMemoryType;
  content: string;
  status: CoreMemoryStatus;
  source_event_ids: string[];
  confirmed_by: string | null;
  confirmed_at: string | null;
  version: number;
  active_from: string | null;
  inactive_at: string | null;
  consent_version: number;
  created_at: string;
  updated_at: string;
}

interface CoreMemoryList {
  items: CoreMemory[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface MemoryView {
  memoryId: string;
  elderId: string;
  memoryType: CoreMemoryType;
  content: string;
  status: CoreMemoryStatus;
  sourceEventIds: string[];
  confirmedBy: string | null;
  confirmedAt: string | null;
  version: number;
  consentVersion: number;
  createdAt: string;
  updatedAt: string;
}

export interface MemoryListView {
  candidates: MemoryView[];
  confirmed: MemoryView[];
}

function toMemoryView(memory: CoreMemory): MemoryView {
  return {
    memoryId: memory.memory_id,
    elderId: memory.elder_id,
    memoryType: memory.memory_type,
    content: memory.content,
    status: memory.status,
    sourceEventIds: memory.source_event_ids,
    confirmedBy: memory.confirmed_by,
    confirmedAt: memory.confirmed_at,
    version: memory.version,
    consentVersion: memory.consent_version,
    createdAt: memory.created_at,
    updatedAt: memory.updated_at,
  };
}

/** Core separates candidates from confirmed memories, so both formal reads are requested. */
export async function listMemories(config: ApiConfig, elderId: string): Promise<MemoryListView> {
  const [candidateResult, confirmedResult] = await Promise.all([
    apiFetch<CoreMemoryList>(config, `/api/v1/elders/${elderId}/memory-candidates?limit=100`),
    apiFetch<CoreMemoryList>(config, `/api/v1/elders/${elderId}/memories?status=ACTIVE&limit=100`),
  ]);
  return {
    candidates: candidateResult.items.map(toMemoryView),
    confirmed: confirmedResult.items.map(toMemoryView),
  };
}

export function rejectMemory(
  config: ApiConfig,
  elderId: string,
  memory: MemoryView,
): Promise<CoreMemory> {
  return apiFetch(config, `/api/v1/elders/${elderId}/memory-candidates/${memory.memoryId}/reject`, {
    method: 'POST',
    headers: { 'Idempotency-Key': createIdempotencyKey('memory-reject') },
    body: JSON.stringify({
      reason_code: 'CAREGIVER_REJECTED_CANDIDATE',
      expected_version: memory.version,
    }),
  });
}

export function deleteMemory(
  config: ApiConfig,
  elderId: string,
  memory: MemoryView,
): Promise<{ memory_id: string; status: 'DELETED' }> {
  return apiFetch(config, `/api/v1/elders/${elderId}/memories/${memory.memoryId}`, {
    method: 'DELETE',
    headers: { 'Idempotency-Key': createIdempotencyKey('memory-delete') },
    body: JSON.stringify({
      reason_code: 'CAREGIVER_REQUESTED_DELETION',
      expected_version: memory.version,
    }),
  });
}
