import { apiFetch, createIdempotencyKey, type ApiConfig } from './client';

export type FamilyShareScope =
  'REPORT_DAILY' | 'REPORT_WEEKLY' | 'REPORT_MONTHLY' | 'REPORT_IMPORTANT_EVENT';

export interface FamilyInvitationStatus {
  invitation_id: string;
  status: 'ISSUED' | 'REDEEMED' | 'EXPIRED' | 'REVOKED' | 'LOCKED';
  share_scope: FamilyShareScope[];
  expires_at: string;
  created_at: string;
}

export interface CreatedFamilyInvitation {
  invitation_id: string;
  invitation_code: string;
  status: 'ISSUED';
  share_scope: FamilyShareScope[];
  expires_at: string;
}

export async function listFamilyInvitations(
  config: ApiConfig,
  elderId: string,
): Promise<FamilyInvitationStatus[]> {
  const response = await apiFetch<{ items: FamilyInvitationStatus[] }>(
    config,
    `/api/v1/elders/${encodeURIComponent(elderId)}/family-invitations`,
  );
  return response.items;
}

export function createFamilyInvitation(
  config: ApiConfig,
  elderId: string,
  inviteeEmail?: string,
): Promise<CreatedFamilyInvitation> {
  return apiFetch<CreatedFamilyInvitation>(
    config,
    `/api/v1/elders/${encodeURIComponent(elderId)}/family-invitations`,
    {
      method: 'POST',
      headers: { 'Idempotency-Key': createIdempotencyKey('family-invitation') },
      body: JSON.stringify({
        ...(inviteeEmail ? { invitee_email: inviteeEmail } : {}),
        share_scope: ['REPORT_DAILY', 'REPORT_WEEKLY', 'REPORT_MONTHLY'],
        expires_in_hours: 24,
      }),
    },
  );
}

export function revokeFamilyInvitation(
  config: ApiConfig,
  elderId: string,
  invitationId: string,
): Promise<FamilyInvitationStatus> {
  return apiFetch<FamilyInvitationStatus>(
    config,
    `/api/v1/elders/${encodeURIComponent(elderId)}/family-invitations/${encodeURIComponent(invitationId)}/revoke`,
    {
      method: 'POST',
      headers: { 'Idempotency-Key': createIdempotencyKey('revoke-family-invitation') },
    },
  );
}
