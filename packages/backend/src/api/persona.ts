import type { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';
import type { PersonaContext, PersonaRecord, UpdatePersonaRequest } from '@elderly-care/shared';
import { DynamoTable, Keys } from '../db/index.js';
import { getAuthContext, jsonResponse, parseBody, requireAuthorization, requirePathParam, withErrorHandling } from './http.js';

const DEFAULT_PERSONA: PersonaContext = {
  displayName: '',
  preferredLanguage: 'zh-TW',
  responseLength: 'medium',
  speakingSpeed: 'normal',
  interactionStyle: 'warm',
  customGreeting: '',
};

/** GET /v1/elders/{elderId}/persona — current settings, or defaults if never saved (caregiver/admin only). */
export const getPersonaHandler = withErrorHandling(async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
  const authContext = getAuthContext(event);
  const elderId = requirePathParam(event, 'elderId');
  requireAuthorization(authContext, 'persona', 'read', elderId);

  const existing = await new DynamoTable().getItem<PersonaRecord>(Keys.elderPk(elderId), Keys.personaSk());
  return jsonResponse(200, existing ?? DEFAULT_PERSONA);
});

/** PUT /v1/elders/{elderId}/persona (A06 prerequisite for personalization; caregiver/admin only). */
export const handler = withErrorHandling(async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
  const authContext = getAuthContext(event);
  const elderId = requirePathParam(event, 'elderId');
  requireAuthorization(authContext, 'persona', 'write', elderId);

  const updates = parseBody<UpdatePersonaRequest>(event);
  const table = new DynamoTable();
  const existing = await table.getItem<PersonaRecord>(Keys.elderPk(elderId), Keys.personaSk());
  const base = existing ?? DEFAULT_PERSONA;

  const merged: PersonaRecord = {
    PK: Keys.elderPk(elderId),
    SK: 'PERSONA',
    elderId,
    displayName: updates.displayName ?? base.displayName,
    preferredLanguage: updates.preferredLanguage ?? base.preferredLanguage,
    responseLength: updates.responseLength ?? base.responseLength,
    speakingSpeed: updates.speakingSpeed ?? base.speakingSpeed,
    interactionStyle: updates.interactionStyle ?? base.interactionStyle,
    customGreeting: updates.customGreeting ?? base.customGreeting,
    updatedAt: new Date().toISOString(),
    updatedBy: updates.updatedBy,
  };

  await table.putItem(merged);
  return jsonResponse(200, merged);
});
