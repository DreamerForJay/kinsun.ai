const SESSION_ENDPOINT = '/backend/auth/session';

interface SessionStatusResponse {
  credential_present?: boolean;
}

async function parseStatus(response: Response): Promise<boolean> {
  if (!response.ok) throw new Error(`AUTH_SESSION_${response.status}`);
  const body = (await response.json()) as SessionStatusResponse;
  return body.credential_present === true;
}

export async function hasAuthCredential(): Promise<boolean> {
  const response = await fetch(SESSION_ENDPOINT, {
    credentials: 'same-origin',
    cache: 'no-store',
  });
  return parseStatus(response);
}

export async function createDevelopmentAuthSession(accessToken: string): Promise<void> {
  const response = await fetch(SESSION_ENDPOINT, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ access_token: accessToken }),
  });
  await parseStatus(response);
}

export async function clearAuthSession(): Promise<void> {
  const response = await fetch(SESSION_ENDPOINT, {
    method: 'DELETE',
    credentials: 'same-origin',
  });
  if (!response.ok) throw new Error(`AUTH_SESSION_${response.status}`);
}
