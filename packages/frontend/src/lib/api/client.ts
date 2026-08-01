export interface ApiConfig {
  apiBaseUrl: string;
}

interface ApiSuccessEnvelope<T> {
  data: T;
  meta: {
    correlation_id: string;
    timestamp: string;
    schema_version: '1.0';
  };
}

interface ApiErrorEnvelope {
  error?: {
    message?: string;
    reason_code?: string | null;
    retryable?: boolean;
  };
}

export class ApiRequestError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly reasonCode?: string,
    public readonly retryable: boolean = false,
  ) {
    super(message);
    this.name = 'ApiRequestError';
  }
}

/**
 * Thin same-origin fetch wrapper shared by every REST client module. Browser
 * JavaScript never reads or attaches credentials: the HttpOnly cookie goes to
 * the Next.js BFF, which adds Core's Bearer header server-side.
 */
export async function apiFetch<T>(
  config: ApiConfig,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const base = config.apiBaseUrl.replace(/\/+$/, '');
  const headers = new Headers(init.headers);
  headers.delete('Authorization');
  if (init.body !== undefined) headers.set('Content-Type', 'application/json');
  const response = await fetch(`${base}${path}`, {
    ...init,
    headers,
    credentials: 'same-origin',
  });

  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorEnvelope;
    throw new ApiRequestError(
      response.status,
      body.error?.message || `Request to ${path} failed with ${response.status}`,
      body.error?.reason_code ?? undefined,
      body.error?.retryable ?? false,
    );
  }

  if (response.status === 204) return undefined as T;
  const envelope = (await response.json()) as ApiSuccessEnvelope<T>;
  return envelope.data;
}

export function createIdempotencyKey(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
}
