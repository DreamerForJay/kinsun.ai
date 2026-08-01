export interface ApiConfig {
  apiBaseUrl: string;
  token: string;
}

export class ApiRequestError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiRequestError';
  }
}

/**
 * Thin authenticated fetch wrapper shared by every REST client module.
 * `apiBaseUrl`'s trailing slash is stripped before joining — CDK's RestApi.url
 * CfnOutput always ends in `/` (e.g. `.../dev/`), and every path here starts
 * with `/v1/...`; pasting the raw CDK output in verbatim would otherwise
 * produce a double slash that API Gateway won't route (404/403, not a clean
 * error), regardless of whether whoever set NEXT_PUBLIC_API_BASE_URL trimmed it.
 */
export async function apiFetch<T>(config: ApiConfig, path: string, init: RequestInit = {}): Promise<T> {
  const base = config.apiBaseUrl.replace(/\/+$/, '');
  const response = await fetch(`${base}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${config.token}`,
      'Content-Type': 'application/json',
      ...init.headers,
    },
  });

  if (!response.ok) {
    const body = await response.text().catch(() => '');
    throw new ApiRequestError(response.status, body || `Request to ${path} failed with ${response.status}`);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
