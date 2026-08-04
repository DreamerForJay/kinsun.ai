type AuthDiagnosticValue = boolean | number | string | null;

/**
 * Emit one bounded, single-string auth diagnostic that remains readable in
 * Next.js development logs. Callers must supply only allowlisted metadata;
 * tokens, authorization codes, state values, email addresses, and provider
 * descriptions must never be passed here.
 */
export function logAuthDiagnostic(
  event: string,
  fields: Record<string, AuthDiagnosticValue>,
): void {
  console.error(`[auth] ${event} ${JSON.stringify(fields)}`);
}
