import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const dockerfile = readFileSync(fileURLToPath(new URL('../Dockerfile', import.meta.url)), 'utf8');
const cachePath = '/app/packages/frontend/.next/cache';

describe('frontend production container contract', () => {
  it('prepares the ECS cache mount before declaring its exact absolute volume path', () => {
    const createIndex = dockerfile.indexOf(`mkdir -p ${cachePath}`);
    const ownershipIndex = dockerfile.indexOf('chown -R nextjs:nodejs /app/packages/frontend/.next');
    const volumeIndex = dockerfile.indexOf(`VOLUME ["${cachePath}"]`);
    const userIndex = dockerfile.indexOf('USER nextjs');

    expect(createIndex).toBeGreaterThan(-1);
    expect(ownershipIndex).toBeGreaterThan(createIndex);
    expect(volumeIndex).toBeGreaterThan(ownershipIndex);
    expect(userIndex).toBeGreaterThan(volumeIndex);
  });

  it('does not accept server credentials as image build arguments', () => {
    const buildArguments = [...dockerfile.matchAll(/^ARG\s+([A-Z0-9_]+)/gm)].map((match) => match[1]);

    expect(buildArguments).toEqual([
      'NODE_VERSION',
      'NEXT_PUBLIC_CONSENT_POLICY_VERSION',
      'NEXT_PUBLIC_WS_URL',
    ]);
  });
});
