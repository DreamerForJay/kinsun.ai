import type { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';
import { DynamoTable } from '../db/index.js';
import { computeReport } from '../report/compute.js';
import { getAuthContext, jsonResponse, requireAuthorization, requirePathParam, withErrorHandling } from './http.js';

/** GET /v1/elders/{elderId}/reports?range=week|year (A07.1-A07.4, caregiver/family-facing). */
export const handler = withErrorHandling(async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
  const authContext = getAuthContext(event);
  const elderId = requirePathParam(event, 'elderId');
  requireAuthorization(authContext, 'event', 'read', elderId);

  const range = (event.queryStringParameters?.range === 'year' ? 'year' : 'week') as 'week' | 'year';
  const response = await computeReport(new DynamoTable(), elderId, range);

  return jsonResponse(200, response);
});
