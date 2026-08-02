import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import * as memoriesApi from './memories';

function source(relativeUrl: string): string {
  return readFileSync(fileURLToPath(new URL(relativeUrl, import.meta.url)), 'utf8');
}

describe('caregiver memory confirmation guard', () => {
  it('does not export or implement a memory-confirmation API', () => {
    expect(memoriesApi).not.toHaveProperty('confirmMemory');

    const apiSource = source('./memories.ts');
    expect(apiSource).not.toContain('/confirm');
    expect(apiSource).not.toContain('CAREGIVER_REVIEW');
  });

  it('does not render or wire a confirmation action on the caregiver dashboard', () => {
    const memoryListSource = source('../../components/dashboard/MemoryList.tsx');
    const dashboardSource = source('../../app/dashboard/[elderId]/page.tsx');

    expect(memoryListSource).not.toContain('onConfirm');
    expect(memoryListSource).not.toContain("t('memory.confirm')");
    expect(dashboardSource).not.toContain('confirmMemory');
    expect(dashboardSource).not.toContain('handleConfirmMemory');
  });
});
