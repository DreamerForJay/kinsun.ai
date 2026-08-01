export function bffError(
  status: number,
  code: string,
  message: string,
  reasonCode: string,
  retryable = false,
): Response {
  return Response.json(
    {
      error: {
        code,
        message,
        reason_code: reasonCode,
        retryable,
      },
      meta: {
        correlation_id: crypto.randomUUID(),
        timestamp: new Date().toISOString(),
        schema_version: '1.0',
      },
    },
    {
      status,
      headers: {
        'Cache-Control': 'no-store',
        'X-Content-Type-Options': 'nosniff',
      },
    },
  );
}
