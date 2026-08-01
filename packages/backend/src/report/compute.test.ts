import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient, QueryCommand } from '@aws-sdk/lib-dynamodb';
import { mockClient } from 'aws-sdk-client-mock';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ConversationRecord, EventRecord } from '@elderly-care/shared';

const docClient = DynamoDBDocumentClient.from(new DynamoDBClient({}));
const ddbMock = mockClient(docClient);

vi.mock('../db/client.js', async () => {
  const actual = await vi.importActual<typeof import('../db/client.js')>('../db/client.js');
  return {
    ...actual,
    DynamoTable: class extends actual.DynamoTable {
      constructor() {
        super(undefined, docClient);
      }
    },
  };
});

const { DynamoTable } = await import('../db/client.js');
const { computeReport } = await import('./compute.js');

function makeEvent(overrides: Partial<EventRecord>): EventRecord {
  return {
    PK: 'ELDER#elder-1',
    SK: `EVENT#${overrides.eventDate ?? '2026-07-30'}#evt-1`,
    GSI1PK: '',
    GSI1SK: '',
    GSI2PK: '',
    GSI2SK: '',
    eventId: 'evt-1',
    elderId: 'elder-1',
    eventType: 'meal',
    content: '早餐吃地瓜稀飯',
    originalUtterance: '我早餐吃了地瓜稀飯',
    eventDate: '2026-07-30',
    confidence: 0.9,
    sourceConversationId: 'conv-1',
    reviewStatus: 'auto_approved',
    reviewHistory: [],
    createdAt: '2026-07-30T00:00:00Z',
    updatedAt: '2026-07-30T00:00:00Z',
    ttl: 0,
    ...overrides,
  };
}

describe('computeReport (A07.1-A07.4)', () => {
  beforeEach(() => {
    ddbMock.reset();
  });

  it('counts only events within the requested range, by type', async () => {
    const inRange = makeEvent({ eventDate: new Date().toISOString().slice(0, 10), eventType: 'meal' });
    const longAgo = makeEvent({ eventDate: '2020-01-01', eventType: 'meal', eventId: 'evt-old' });

    ddbMock.on(QueryCommand).callsFake((input) => {
      if ((input.ExpressionAttributeValues?.[':skPrefix'] as string)?.startsWith('EVENT#')) {
        return { Items: [inRange, longAgo] };
      }
      return { Items: [] };
    });

    const table = new DynamoTable();
    const report = await computeReport(table, 'elder-1', 'week');

    expect(report.eventCountByType.meal).toBe(1);
    expect(report.range).toBe('week');
  });

  it('never fabricates a data point beyond what is in DynamoDB (A07.4)', async () => {
    ddbMock.on(QueryCommand).resolves({ Items: [] });
    const table = new DynamoTable();
    const report = await computeReport(table, 'elder-1', 'week');

    expect(report.totalInteractions).toBe(0);
    Object.values(report.eventCountByType).forEach((count) => expect(count).toBe(0));
    expect(report.voiceSummary).toContain('0 次');
  });

  it('counts conversations within range as totalInteractions', async () => {
    const recentConversation: ConversationRecord = {
      PK: 'ELDER#elder-1',
      SK: 'CONV#x',
      conversationId: 'conv-1',
      elderId: 'elder-1',
      startTime: new Date().toISOString(),
      endTime: null,
      turns: [],
      asrMetadata: null,
      status: 'completed',
      traceId: 't1',
      audioS3Key: null,
      ttl: 0,
    };

    ddbMock.on(QueryCommand).callsFake((input) => {
      const prefix = input.ExpressionAttributeValues?.[':skPrefix'] as string | undefined;
      if (prefix?.startsWith('CONV#')) return { Items: [recentConversation] };
      return { Items: [] };
    });

    const table = new DynamoTable();
    const report = await computeReport(table, 'elder-1', 'week');
    expect(report.totalInteractions).toBe(1);
  });
});
