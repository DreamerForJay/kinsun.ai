import { randomUUID } from 'node:crypto';
import type { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';
import type { HealthSearchRequest, HealthSearchResponse } from '@elderly-care/shared';
import {
  AgentRuntimeRagClient,
  RagClientConfigurationError,
  RagClientHttpError,
  RagClientProtocolError,
  RagClientRequestError,
  RagClientTimeoutError,
  RagClientTransportError,
  type RagQueryProfile,
} from '../search/client.js';
import {
  getAuthContext,
  HttpError,
  jsonResponse,
  parseBody,
  requireAuthorization,
  withErrorHandling,
} from './http.js';

interface HealthSearchProxyRequest extends HealthSearchRequest {
  queryProfile?: RagQueryProfile;
}

const RAG_AUDIENCE_BY_ROLE = {
  elder: 'elder',
  caregiver: 'care_professional',
  family: 'family_caregiver',
  admin: 'system_admin',
} as const;

let cachedClient: AgentRuntimeRagClient | null = null;
function getRagClient(): AgentRuntimeRagClient {
  cachedClient ??= new AgentRuntimeRagClient();
  return cachedClient;
}

const LEGACY_DISCLAIMER = '僅供參考，不作為醫療診斷依據';

function toLegacyHealthSearchResponse(
  response: Awaited<ReturnType<AgentRuntimeRagClient['retrieve']>>,
): HealthSearchResponse {
  if (response.status !== 'SUCCESS') {
    return {
      answer: response.fallback_message ?? '目前無法取得可靠資料，請稍後再試。',
      sources: [],
      disclaimer: LEGACY_DISCLAIMER,
      grounded: false,
    };
  }

  // This legacy contract cannot represent URL/page/section citations. Do not
  // concatenate retrieved chunks and present them as a generated answer.
  return {
    answer: '已找到相關來源，但具引用的回答生成尚未接線；目前不提供推測性回答。',
    sources: [],
    disclaimer: LEGACY_DISCLAIMER,
    grounded: false,
  };
}

function getCorrelationId(event: APIGatewayProxyEvent): string | undefined {
  const entry = Object.entries(event.headers ?? {}).find(
    ([name]) => name.toLowerCase() === 'x-correlation-id',
  );
  return entry?.[1] ?? undefined;
}

function mapRagClientError(error: unknown): never {
  if (error instanceof RagClientConfigurationError) {
    throw new HttpError(503, 'RAG_NOT_CONFIGURED', 'Knowledge retrieval is not configured');
  }
  if (error instanceof RagClientRequestError) {
    throw new HttpError(400, 'BAD_REQUEST', 'The retrieval request is invalid');
  }
  if (error instanceof RagClientTimeoutError) {
    throw new HttpError(504, 'RAG_UPSTREAM_TIMEOUT', 'Knowledge retrieval timed out');
  }
  if (
    error instanceof RagClientHttpError ||
    error instanceof RagClientProtocolError ||
    error instanceof RagClientTransportError
  ) {
    throw new HttpError(502, 'RAG_UPSTREAM_ERROR', 'Knowledge retrieval is unavailable');
  }
  throw error;
}

/**
 * Legacy edge route retained for callers that still use POST /v1/search/health.
 * Authorization remains here; retrieval itself is owned by agent-runtime.
 */
export const handler = withErrorHandling(
  async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
    const authContext = getAuthContext(event);
    const {
      elderId,
      question,
      queryProfile = 'natural_language',
    } = parseBody<HealthSearchProxyRequest>(event);
    // There is no dedicated health-query resource yet; elder-scoped summary
    // read is the existing authorization bar.
    requireAuthorization(authContext, 'summary', 'read', elderId);

    const requestId = `rag-${randomUUID()}`;
    try {
      const response = await getRagClient().retrieve(
        {
          schema_version: '1.0.0',
          request_id: requestId,
          query: question,
          query_profile: queryProfile,
          top_k: 5,
          audience: RAG_AUDIENCE_BY_ROLE[authContext.role],
          purpose: queryProfile === 'legal' ? 'legal_reference' : 'general_information',
          language: 'zh-TW',
        },
        { correlationId: getCorrelationId(event) ?? requestId },
      );
      return jsonResponse(200, toLegacyHealthSearchResponse(response));
    } catch (error) {
      return mapRagClientError(error);
    }
  },
);
