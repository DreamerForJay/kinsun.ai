import { describe, expect, it } from 'vitest';
import {
  AgentRuntimeRagClient,
  RagClientHttpError,
  RagClientProtocolError,
  RagClientTimeoutError,
  type RagRetrievalRequest,
  type RagRetrievalResponse,
  type RagRetrievalSuccessEnvelope,
} from './client.js';

const REQUEST: RagRetrievalRequest = {
  schema_version: '1.0.0',
  request_id: 'req-rag-001',
  query: '長照服務的申請資格是什麼？',
  query_profile: 'natural_language',
  top_k: 5,
  language: 'zh-TW',
};

const RESPONSE: RagRetrievalResponse = {
  schema_version: '1.0.0',
  request_id: REQUEST.request_id,
  status: 'SUCCESS',
  fallback_message: null,
  results: [
    {
      chunk_id: 'chunk-approved-001',
      text: '這是合成測試用的長照法規內容。',
      score: 0.91,
      document_name: '長期照顧服務法',
      section: '第一章 總則',
      page_start: 1,
      page_end: 1,
      source_url: 'https://example.invalid/synthetic-source',
    },
    {
      chunk_id: 'chunk-approved-002',
      text: '這是第二筆合成測試內容。',
      score: 0.84,
      document_name: '長期照顧服務法',
      section: '第二章 長照服務',
      page_start: 2,
      page_end: 2,
      source_url: 'https://example.invalid/synthetic-source',
    },
    {
      chunk_id: 'chunk-approved-003',
      text: '這是第三筆合成測試內容。',
      score: 0.79,
      document_name: '長期照顧服務法',
      section: '第三章 人員管理',
      page_start: 3,
      page_end: 3,
      source_url: 'https://example.invalid/synthetic-source',
    },
  ],
};

function successEnvelope(data: RagRetrievalResponse): RagRetrievalSuccessEnvelope {
  return {
    data,
    meta: {
      correlation_id: 'corr-rag-001',
      timestamp: '2026-08-01T04:00:00Z',
      schema_version: '1.0',
    },
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('AgentRuntimeRagClient', () => {
  it('sends the retrieval contract with environment base URL and correlation id', async () => {
    const previousBaseUrl = process.env.AGENT_RUNTIME_BASE_URL;
    process.env.AGENT_RUNTIME_BASE_URL = 'http://agent-runtime.test/';

    let capturedInput: Parameters<typeof fetch>[0] | undefined;
    let capturedInit: Parameters<typeof fetch>[1];
    const fetchFn: typeof fetch = async (input, init) => {
      capturedInput = input;
      capturedInit = init;
      return jsonResponse(successEnvelope(RESPONSE));
    };

    try {
      const client = new AgentRuntimeRagClient({ fetchFn, timeoutMs: 1_000 });
      const result = await client.retrieve(REQUEST, { correlationId: 'corr-rag-001' });

      expect(result).toEqual(RESPONSE);
      expect(capturedInput).toBe('http://agent-runtime.test/api/v1/rag/retrievals');
      expect(capturedInit?.method).toBe('POST');
      expect(capturedInit?.headers).toEqual({
        'Content-Type': 'application/json',
        'x-correlation-id': 'corr-rag-001',
      });
      expect(JSON.parse(capturedInit?.body as string)).toEqual(REQUEST);
    } finally {
      if (previousBaseUrl === undefined) delete process.env.AGENT_RUNTIME_BASE_URL;
      else process.env.AGENT_RUNTIME_BASE_URL = previousBaseUrl;
    }
  });

  it('passes through an explicit no-data fallback without inventing results', async () => {
    const noData: RagRetrievalResponse = {
      ...RESPONSE,
      status: 'NO_DATA',
      fallback_message: '目前查無可引用資料，請洽照護專業人員。',
      results: [],
    };
    const fetchFn: typeof fetch = async () => jsonResponse(successEnvelope(noData));
    const client = new AgentRuntimeRagClient({ baseUrl: 'http://agent-runtime.test', fetchFn });

    await expect(client.retrieve(REQUEST)).resolves.toEqual(noData);
  });

  it('rejects an upstream response that violates the retrieval response contract', async () => {
    const fetchFn: typeof fetch = async () =>
      jsonResponse({
        data: {
          ...RESPONSE,
          results: [
            { ...RESPONSE.results[0]!, source_url: undefined },
            ...RESPONSE.results.slice(1),
          ],
        },
        meta: successEnvelope(RESPONSE).meta,
      });
    const client = new AgentRuntimeRagClient({ baseUrl: 'http://agent-runtime.test', fetchFn });

    await expect(client.retrieve(REQUEST)).rejects.toBeInstanceOf(RagClientProtocolError);
  });

  it('rejects a result without a concrete section and page citation', async () => {
    const fetchFn: typeof fetch = async () =>
      jsonResponse({
        data: {
          ...RESPONSE,
          results: [
            { ...RESPONSE.results[0]!, section: null, page_start: null },
            ...RESPONSE.results.slice(1),
          ],
        },
        meta: successEnvelope(RESPONSE).meta,
      });
    const client = new AgentRuntimeRagClient({ baseUrl: 'http://agent-runtime.test', fetchFn });

    await expect(client.retrieve(REQUEST)).rejects.toBeInstanceOf(RagClientProtocolError);
  });

  it('rejects a naked domain response or extra envelope metadata', async () => {
    const nakedFetch: typeof fetch = async () => jsonResponse(RESPONSE);
    const extraMetaFetch: typeof fetch = async () =>
      jsonResponse({
        ...successEnvelope(RESPONSE),
        meta: { ...successEnvelope(RESPONSE).meta, unexpected: true },
      });

    const nakedClient = new AgentRuntimeRagClient({
      baseUrl: 'http://agent-runtime.test',
      fetchFn: nakedFetch,
    });
    const extraMetaClient = new AgentRuntimeRagClient({
      baseUrl: 'http://agent-runtime.test',
      fetchFn: extraMetaFetch,
    });

    await expect(nakedClient.retrieve(REQUEST)).rejects.toBeInstanceOf(RagClientProtocolError);
    await expect(extraMetaClient.retrieve(REQUEST)).rejects.toBeInstanceOf(RagClientProtocolError);
  });

  it('does not include an upstream body or the query in HTTP errors', async () => {
    const fetchFn: typeof fetch = async () => jsonResponse({ rejected_query: REQUEST.query }, 503);
    const client = new AgentRuntimeRagClient({ baseUrl: 'http://agent-runtime.test', fetchFn });

    let error: unknown;
    try {
      await client.retrieve(REQUEST);
    } catch (caught) {
      error = caught;
    }

    expect(error).toBeInstanceOf(RagClientHttpError);
    expect((error as Error).message).not.toContain(REQUEST.query);
    expect((error as Error).message).not.toContain('rejected_query');
  });

  it('aborts a slow request at the configured timeout', async () => {
    const fetchFn: typeof fetch = async (_input, init) =>
      await new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
      });
    const client = new AgentRuntimeRagClient({
      baseUrl: 'http://agent-runtime.test',
      fetchFn,
      timeoutMs: 5,
    });

    await expect(client.retrieve(REQUEST)).rejects.toBeInstanceOf(RagClientTimeoutError);
  });
});
