const RETRIEVAL_PATH = '/api/v1/rag/retrievals';
const DEFAULT_TIMEOUT_MS = 5_000;
const REQUEST_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{1,127}$/;
const LANGUAGE_PATTERN = /^[a-z]{2,3}(?:-[A-Za-z]{2})?$/;

export type RagQueryProfile = 'natural_language' | 'legal';
export type RagRetrievalStatus = 'SUCCESS' | 'NO_DATA' | 'FAILED';

export interface RagRetrievalRequest {
  schema_version: '1.0.0';
  request_id: string;
  query: string;
  query_profile: RagQueryProfile;
  top_k: 5;
  audience?: string | null;
  purpose?: string | null;
  language?: string;
}

export interface RagRetrievalResult {
  chunk_id: string;
  text: string;
  score: number;
  document_name: string;
  section: string;
  page_start: number;
  page_end: number;
  source_url: string;
}

export interface RagRetrievalResponse {
  schema_version: '1.0.0';
  request_id: string;
  status: RagRetrievalStatus;
  fallback_message: string | null;
  results: RagRetrievalResult[];
}

export interface RagResponseMeta {
  correlation_id: string;
  timestamp: string;
  schema_version: '1.0';
}

export interface RagRetrievalSuccessEnvelope {
  data: RagRetrievalResponse;
  meta: RagResponseMeta;
}

export interface AgentRuntimeRagClientConfig {
  /** Defaults to AGENT_RUNTIME_BASE_URL. The URL may be HTTP for local development. */
  baseUrl?: string;
  timeoutMs?: number;
  fetchFn?: typeof fetch;
}

export interface RagRetrieveOptions {
  correlationId?: string;
}

export class RagClientError extends Error {}

export class RagClientConfigurationError extends RagClientError {
  constructor(message: string) {
    super(message);
    this.name = 'RagClientConfigurationError';
  }
}

export class RagClientRequestError extends RagClientError {
  constructor(message: string) {
    super(message);
    this.name = 'RagClientRequestError';
  }
}

export class RagClientTimeoutError extends RagClientError {
  public readonly timeoutMs: number;

  constructor(timeoutMs: number) {
    super(`Agent runtime retrieval timed out after ${timeoutMs} ms.`);
    this.name = 'RagClientTimeoutError';
    this.timeoutMs = timeoutMs;
  }
}

export class RagClientHttpError extends RagClientError {
  public readonly status: number;

  constructor(status: number) {
    // Deliberately omit the upstream body: it must not echo the elder's query.
    super(`Agent runtime retrieval failed with HTTP ${status}.`);
    this.name = 'RagClientHttpError';
    this.status = status;
  }
}

export class RagClientTransportError extends RagClientError {
  constructor() {
    super('Agent runtime retrieval request failed.');
    this.name = 'RagClientTransportError';
  }
}

export class RagClientProtocolError extends RagClientError {
  constructor(reason: string) {
    super(`Agent runtime retrieval response failed contract validation: ${reason}.`);
    this.name = 'RagClientProtocolError';
  }
}

function normalizeBaseUrl(value: string | undefined): string {
  if (!value) {
    throw new RagClientConfigurationError('AGENT_RUNTIME_BASE_URL is not configured.');
  }

  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new RagClientConfigurationError('AGENT_RUNTIME_BASE_URL must be a valid URL.');
  }

  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new RagClientConfigurationError('AGENT_RUNTIME_BASE_URL must use HTTP or HTTPS.');
  }

  return value.replace(/\/+$/, '');
}

function assertOptionalString(
  value: string | null | undefined,
  field: string,
  maxLength: number,
): void {
  if (
    value !== undefined &&
    value !== null &&
    (typeof value !== 'string' || value.length > maxLength)
  ) {
    throw new RagClientRequestError(`${field} is invalid.`);
  }
}

function validateRequest(request: RagRetrievalRequest): void {
  const allowedKeys = new Set([
    'schema_version',
    'request_id',
    'query',
    'query_profile',
    'top_k',
    'audience',
    'purpose',
    'language',
  ]);
  if (Object.keys(request).some((key) => !allowedKeys.has(key))) {
    throw new RagClientRequestError('request contains an unsupported property.');
  }
  if (request.schema_version !== '1.0.0') {
    throw new RagClientRequestError('schema_version is invalid.');
  }
  if (typeof request.request_id !== 'string' || !REQUEST_ID_PATTERN.test(request.request_id)) {
    throw new RagClientRequestError('request_id is invalid.');
  }
  if (
    typeof request.query !== 'string' ||
    request.query.length < 1 ||
    request.query.length > 2_000 ||
    !request.query.trim()
  ) {
    throw new RagClientRequestError('query is invalid.');
  }
  if (request.query_profile !== 'natural_language' && request.query_profile !== 'legal') {
    throw new RagClientRequestError('query_profile is invalid.');
  }
  if (request.top_k !== 5) {
    throw new RagClientRequestError('top_k must be 5.');
  }
  assertOptionalString(request.audience, 'audience', 80);
  assertOptionalString(request.purpose, 'purpose', 120);
  if (
    request.language !== undefined &&
    (typeof request.language !== 'string' || !LANGUAGE_PATTERN.test(request.language))
  ) {
    throw new RagClientRequestError('language is invalid.');
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function assertNoExtraProperties(
  value: Record<string, unknown>,
  allowed: readonly string[],
  field: string,
): void {
  const allowedKeys = new Set(allowed);
  if (Object.keys(value).some((key) => !allowedKeys.has(key))) {
    throw new RagClientProtocolError(`${field} contains an unsupported property`);
  }
}

function assertNullableString(value: unknown, field: string, maxLength: number): void {
  if (value !== null && (typeof value !== 'string' || value.length > maxLength)) {
    throw new RagClientProtocolError(`${field} is invalid`);
  }
}

function assertPositiveInteger(value: unknown, field: string): asserts value is number {
  if (!Number.isInteger(value) || (value as number) < 1) {
    throw new RagClientProtocolError(`${field} is invalid`);
  }
}

function validateResult(value: unknown, index: number): asserts value is RagRetrievalResult {
  if (!isRecord(value)) {
    throw new RagClientProtocolError(`results[${index}] is invalid`);
  }
  assertNoExtraProperties(
    value,
    [
      'chunk_id',
      'text',
      'score',
      'document_name',
      'section',
      'page_start',
      'page_end',
      'source_url',
    ],
    `results[${index}]`,
  );

  if (
    typeof value.chunk_id !== 'string' ||
    value.chunk_id.length < 1 ||
    value.chunk_id.length > 256
  ) {
    throw new RagClientProtocolError(`results[${index}].chunk_id is invalid`);
  }
  if (typeof value.text !== 'string' || value.text.length < 1 || value.text.length > 50_000) {
    throw new RagClientProtocolError(`results[${index}].text is invalid`);
  }
  if (typeof value.score !== 'number' || !Number.isFinite(value.score)) {
    throw new RagClientProtocolError(`results[${index}].score is invalid`);
  }
  if (
    typeof value.document_name !== 'string' ||
    value.document_name.length < 1 ||
    value.document_name.length > 512
  ) {
    throw new RagClientProtocolError(`results[${index}].document_name is invalid`);
  }
  if (typeof value.section !== 'string' || value.section.length < 1 || value.section.length > 512) {
    throw new RagClientProtocolError(`results[${index}].section is invalid`);
  }
  assertPositiveInteger(value.page_start, `results[${index}].page_start`);
  assertPositiveInteger(value.page_end, `results[${index}].page_end`);
  if (typeof value.source_url !== 'string' || value.source_url.length > 2_048) {
    throw new RagClientProtocolError(`results[${index}].source_url is invalid`);
  }
  let parsedSourceUrl: URL;
  try {
    parsedSourceUrl = new URL(value.source_url);
  } catch {
    throw new RagClientProtocolError(`results[${index}].source_url is invalid`);
  }
  if (parsedSourceUrl.protocol !== 'http:' && parsedSourceUrl.protocol !== 'https:') {
    throw new RagClientProtocolError(`results[${index}].source_url is invalid`);
  }
  if (value.page_end < value.page_start) {
    throw new RagClientProtocolError(`results[${index}] has an invalid page range`);
  }
}

function validateResponse(
  value: unknown,
  requestId: string,
): asserts value is RagRetrievalResponse {
  if (!isRecord(value)) {
    throw new RagClientProtocolError('response body is invalid');
  }
  assertNoExtraProperties(
    value,
    ['schema_version', 'request_id', 'status', 'fallback_message', 'results'],
    'response body',
  );
  if (value.schema_version !== '1.0.0') {
    throw new RagClientProtocolError('schema_version is invalid');
  }
  if (value.request_id !== requestId) {
    throw new RagClientProtocolError('request_id does not match');
  }
  if (value.status !== 'SUCCESS' && value.status !== 'NO_DATA' && value.status !== 'FAILED') {
    throw new RagClientProtocolError('status is invalid');
  }
  assertNullableString(value.fallback_message, 'fallback_message', 1_000);
  if (!Array.isArray(value.results) || value.results.length > 5) {
    throw new RagClientProtocolError('results is invalid');
  }
  value.results.forEach((result, index) => validateResult(result, index));
  if (value.status === 'SUCCESS') {
    if (value.fallback_message !== null || value.results.length < 3) {
      throw new RagClientProtocolError('successful response is inconsistent');
    }
  } else if (
    typeof value.fallback_message !== 'string' ||
    !value.fallback_message.trim() ||
    value.results.length !== 0
  ) {
    throw new RagClientProtocolError('fallback response is inconsistent');
  }
}

function validateMeta(value: unknown): asserts value is RagResponseMeta {
  if (!isRecord(value)) {
    throw new RagClientProtocolError('meta is invalid');
  }
  assertNoExtraProperties(value, ['correlation_id', 'timestamp', 'schema_version'], 'meta');
  if (typeof value.correlation_id !== 'string' || value.correlation_id.length < 1) {
    throw new RagClientProtocolError('meta.correlation_id is invalid');
  }
  if (
    typeof value.timestamp !== 'string' ||
    !/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value.timestamp) ||
    Number.isNaN(Date.parse(value.timestamp))
  ) {
    throw new RagClientProtocolError('meta.timestamp is invalid');
  }
  if (value.schema_version !== '1.0') {
    throw new RagClientProtocolError('meta.schema_version is invalid');
  }
}

function validateEnvelope(
  value: unknown,
  requestId: string,
): asserts value is RagRetrievalSuccessEnvelope {
  if (!isRecord(value)) {
    throw new RagClientProtocolError('success envelope is invalid');
  }
  assertNoExtraProperties(value, ['data', 'meta'], 'success envelope');
  validateResponse(value.data, requestId);
  validateMeta(value.meta);
}

/**
 * Thin server-to-server client for agent-runtime retrieval.
 *
 * This module intentionally contains no Bedrock/OpenSearch logic and never logs
 * or embeds the query in an exception message.
 */
export class AgentRuntimeRagClient {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;
  private readonly fetchFn: typeof fetch;

  constructor(config: AgentRuntimeRagClientConfig = {}) {
    this.baseUrl = normalizeBaseUrl(config.baseUrl ?? process.env.AGENT_RUNTIME_BASE_URL);
    this.timeoutMs = config.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    if (!Number.isInteger(this.timeoutMs) || this.timeoutMs < 1) {
      throw new RagClientConfigurationError('RAG client timeout must be a positive integer.');
    }
    this.fetchFn = config.fetchFn ?? fetch;
  }

  async retrieve(
    request: RagRetrievalRequest,
    options: RagRetrieveOptions = {},
  ): Promise<RagRetrievalResponse> {
    validateRequest(request);

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (options.correlationId) headers['x-correlation-id'] = options.correlationId;

    let response: Response;
    try {
      response = await this.fetchFn(`${this.baseUrl}${RETRIEVAL_PATH}`, {
        method: 'POST',
        headers,
        body: JSON.stringify(request),
        signal: controller.signal,
      });
    } catch {
      if (controller.signal.aborted) throw new RagClientTimeoutError(this.timeoutMs);
      throw new RagClientTransportError();
    } finally {
      clearTimeout(timeout);
    }

    if (!response.ok) throw new RagClientHttpError(response.status);

    let body: unknown;
    try {
      body = await response.json();
    } catch {
      throw new RagClientProtocolError('response body is not JSON');
    }

    validateEnvelope(body, request.request_id);
    return body.data;
  }
}
