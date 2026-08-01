import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient, QueryCommand } from '@aws-sdk/lib-dynamodb';
import { mockClient } from 'aws-sdk-client-mock';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ContextResult } from '../../context/types.js';

const docClient = DynamoDBDocumentClient.from(new DynamoDBClient({}));
const ddbMock = mockClient(docClient);

vi.mock('../../db/client.js', async () => {
  const actual = await vi.importActual<typeof import('../../db/client.js')>('../../db/client.js');
  return {
    ...actual,
    DynamoTable: class extends actual.DynamoTable {
      constructor() {
        super(undefined, docClient);
      }
    },
  };
});

const { handler } = await import('./llm-handler.js');

const emptyContext: ContextResult = {
  systemPrompt: 'system',
  persona: {
    displayName: '阿嬤',
    preferredLanguage: 'zh-TW',
    responseLength: 'medium',
    speakingSpeed: 'normal',
    interactionStyle: 'warm',
    customGreeting: '',
  },
  recentSummary: null,
  confirmedMemories: [],
  situationalContext: {
    currentTime: '2026-07-30T09:00:00Z',
    dayOfWeek: 'Thursday',
    weather: null,
    recentInteractionCount: 0,
    lastInteractionTime: null,
  },
  searchResults: null,
  usedItems: [],
  totalTokens: 0,
};

describe('llm-handler — report-intent shortcut (A07.3, A07.4)', () => {
  beforeEach(() => {
    ddbMock.reset();
  });

  it('bypasses the LLM and returns a schema-grounded voice summary for a report request', async () => {
    ddbMock.on(QueryCommand).resolves({ Items: [] });

    const result = await handler({
      elderId: 'elder-1',
      traceId: 't1',
      asrResult: {
        degraded: false,
        text: '我這禮拜過得如何？',
        language: 'zh-TW',
        confidence: 0.95,
        serviceEndpoint: 'x',
        modelVersion: 'x',
        latencyMs: 100,
      },
      contextResult: emptyContext,
    });

    expect(result.modelId).toBe('report-query-shortcut');
    expect(result.stopReason).toBe('report_query');
    expect(result.replyText).toContain('這一週');
    expect(result.replyText).toContain('0 次');
  });

  it('does not treat an ordinary utterance as a report request', async () => {
    const result = await import('../../report/intent.js').then((m) => m.detectReportIntent('今天天氣真好，我去公園散步了'));
    expect(result).toBeNull();
  });
});
