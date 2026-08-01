import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient, GetCommand, PutCommand } from '@aws-sdk/lib-dynamodb';
import { mockClient } from 'aws-sdk-client-mock';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { APIGatewayProxyEvent } from 'aws-lambda';
import type { PersonaRecord } from '@elderly-care/shared';

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

const { getPersonaHandler, handler: updatePersonaHandler } = await import('./persona.js');

function fakeEvent(
  overrides: Partial<APIGatewayProxyEvent>,
  authorizer: Record<string, unknown> = { userId: 'cg1', role: 'caregiver', tenantId: 't1', authorizedElderIds: 'elder-1' },
): APIGatewayProxyEvent {
  return {
    body: null,
    headers: {},
    pathParameters: null,
    queryStringParameters: null,
    requestContext: { authorizer } as never,
    ...overrides,
  } as APIGatewayProxyEvent;
}

describe('getPersonaHandler', () => {
  beforeEach(() => {
    ddbMock.reset();
  });

  it('rejects family/elder roles (persona read is caregiver/admin only)', async () => {
    const res = await getPersonaHandler(
      fakeEvent(
        { pathParameters: { elderId: 'elder-1' } },
        { userId: 'fm1', role: 'family', tenantId: 't1', authorizedElderIds: 'elder-1' },
      ),
    );
    expect(res.statusCode).toBe(403);
  });

  it('returns sensible defaults when no persona has ever been saved', async () => {
    ddbMock.on(GetCommand).resolves({ Item: undefined });
    const res = await getPersonaHandler(fakeEvent({ pathParameters: { elderId: 'elder-1' } }));
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.preferredLanguage).toBe('zh-TW');
    expect(body.responseLength).toBe('medium');
  });

  it('returns the saved persona when one exists', async () => {
    const saved: PersonaRecord = {
      PK: 'ELDER#elder-1',
      SK: 'PERSONA',
      elderId: 'elder-1',
      displayName: '阿嬤',
      preferredLanguage: 'nan-TW',
      responseLength: 'short',
      speakingSpeed: 'slow',
      interactionStyle: 'warm',
      customGreeting: '早安！',
      updatedAt: '2026-07-24T00:00:00Z',
      updatedBy: 'cg1',
    };
    ddbMock.on(GetCommand).resolves({ Item: saved });
    const res = await getPersonaHandler(fakeEvent({ pathParameters: { elderId: 'elder-1' } }));
    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).displayName).toBe('阿嬤');
  });
});

describe('updatePersonaHandler (PUT)', () => {
  beforeEach(() => {
    ddbMock.reset();
  });

  it('merges a partial update onto existing defaults instead of wiping unset fields', async () => {
    ddbMock.on(GetCommand).resolves({ Item: undefined });
    ddbMock.on(PutCommand).resolves({});

    const res = await updatePersonaHandler(
      fakeEvent({
        pathParameters: { elderId: 'elder-1' },
        body: JSON.stringify({ displayName: '阿嬤', updatedBy: 'cg1' }),
      }),
    );

    expect(res.statusCode).toBe(200);
    const saved = ddbMock.commandCalls(PutCommand)[0]!.args[0].input.Item as PersonaRecord;
    expect(saved.displayName).toBe('阿嬤');
    expect(saved.preferredLanguage).toBe('zh-TW'); // untouched field keeps its default
  });
});
