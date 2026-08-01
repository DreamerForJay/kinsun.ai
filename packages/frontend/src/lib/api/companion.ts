import { apiFetch, createIdempotencyKey, type ApiConfig } from './client';

export interface VoiceSession {
  session_id: string;
  elder_id: string;
  state:
    'CREATED' | 'RECORDING' | 'PROCESSING' | 'RESPONDING' | 'COMPLETED' | 'CANCELLED' | 'FAILED';
  language_route: 'ZH_TW' | 'NAN_TW' | 'HAK_TW' | 'EN_US' | 'MIXED' | 'UNKNOWN';
  consent_version: number;
  policy_version: string | null;
  transport_status: 'NOT_CONFIGURED' | 'AVAILABLE';
}

export interface CompanionTurn {
  session_id: string;
  agent_run_id: string;
  trace_id: string;
  context_manifest_id: string;
  reply_text: string;
  reply_language: string;
  result_status: 'SUCCESS' | 'BLOCKED' | 'SAFE_FALLBACK' | 'FAILED';
  safety_decision: 'ALLOW' | 'BLOCK' | 'SAFE_FALLBACK' | 'HUMAN_REVIEW';
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  reason_codes: string[];
  session_state: 'COMPLETED';
  transport_status: 'TEXT_ONLY';
  model_route: string;
}

export function createTextSession(config: ApiConfig, elderId: string): Promise<VoiceSession> {
  return apiFetch(config, `/api/v1/elders/${elderId}/voice-sessions`, {
    method: 'POST',
    headers: { 'Idempotency-Key': createIdempotencyKey('text-session') },
    body: JSON.stringify({
      language_preference: 'ZH_TW',
      input_mode: 'text',
      client_timezone: 'Asia/Taipei',
      purpose: 'BASIC_VOICE',
    }),
  });
}

export function runCompanionTurn(
  config: ApiConfig,
  sessionId: string,
  inputText: string,
): Promise<CompanionTurn> {
  return apiFetch(config, `/api/v1/voice-sessions/${sessionId}/companion-turns`, {
    method: 'POST',
    headers: { 'Idempotency-Key': createIdempotencyKey('companion-turn') },
    body: JSON.stringify({ input_text: inputText }),
  });
}
