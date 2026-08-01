import { ApiRequestError, apiFetch, type ApiConfig } from './client';

type ActorRole = 'DAYCARE_CARE_WORKER' | 'HOME_CARE_WORKER' | 'FAMILY_MEMBER' | string;
type ElderMode = 'daycare' | 'home-care' | 'family';

interface ActorProfile {
  role: ActorRole;
}

interface AuthorizedElderItem {
  elder_id: string;
  display_name: string;
  care_unit_name: string | null;
  authorization_summary: string | null;
}

interface AuthorizedElderList {
  items: AuthorizedElderItem[];
  page: {
    next_cursor: string | null;
    has_more: boolean;
    limit: number;
  };
}

export interface DashboardElder {
  elderId: string;
  elderName: string;
  careUnitName: string | null;
  authorizationSummary: string | null;
}

export interface CaregiverDashboard {
  elders: DashboardElder[];
}

function modeForRole(role: ActorRole): ElderMode {
  if (role === 'DAYCARE_CARE_WORKER') return 'daycare';
  if (role === 'HOME_CARE_WORKER') return 'home-care';
  if (role === 'FAMILY_MEMBER') return 'family';
  throw new ApiRequestError(403, '目前身分不支援授權長者清單');
}

/**
 * Core derives the actor from authentication. The browser never sends a
 * caregiver ID and only selects the mode allowed by the authenticated role.
 */
export async function getCaregiverDashboard(config: ApiConfig): Promise<CaregiverDashboard> {
  const profile = await apiFetch<ActorProfile>(config, '/api/v1/me');
  const mode = modeForRole(profile.role);
  const result = await apiFetch<AuthorizedElderList>(
    config,
    `/api/v1/me/authorized-elders?mode=${encodeURIComponent(mode)}&limit=100`,
  );

  return {
    elders: result.items.map((item) => ({
      elderId: item.elder_id,
      elderName: item.display_name,
      careUnitName: item.care_unit_name,
      authorizationSummary: item.authorization_summary,
    })),
  };
}
