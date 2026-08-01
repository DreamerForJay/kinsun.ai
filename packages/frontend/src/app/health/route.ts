export const dynamic = 'force-dynamic';

/**
 * Process liveness only. Dependency readiness belongs to the downstream
 * services, so this response never reflects configuration, credentials, or
 * tenant data.
 */
export function GET(): Response {
  return Response.json(
    { status: 'ok' },
    {
      headers: {
        'Cache-Control': 'no-store',
        'X-Content-Type-Options': 'nosniff',
      },
    },
  );
}
