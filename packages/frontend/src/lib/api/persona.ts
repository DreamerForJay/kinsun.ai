import type { PersonaContext, UpdatePersonaRequest } from '@elderly-care/shared';
import { apiFetch, type ApiConfig } from './client';

/** GET /v1/elders/{elderId}/persona — current settings, or defaults if never saved. */
export function getPersona(config: ApiConfig, elderId: string): Promise<PersonaContext> {
  return apiFetch(config, `/v1/elders/${elderId}/persona`);
}

/** PUT /v1/elders/{elderId}/persona */
export function updatePersona(config: ApiConfig, elderId: string, updates: UpdatePersonaRequest): Promise<PersonaContext> {
  return apiFetch(config, `/v1/elders/${elderId}/persona`, { method: 'PUT', body: JSON.stringify(updates) });
}
