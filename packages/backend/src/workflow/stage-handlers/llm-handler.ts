import { DynamoTable } from '../../db/index.js';
import { LlmEngine } from '../../llm/engine.js';
import type { LlmGenerateResult } from '../../llm/types.js';
import type { ContextResult } from '../../context/types.js';
import { computeReport } from '../../report/compute.js';
import { detectReportIntent } from '../../report/intent.js';
import type { AsrStageOutput } from './asr-handler.js';

export interface LlmStageInput {
  elderId: string;
  traceId: string;
  asrResult: AsrStageOutput;
  contextResult: ContextResult;
}

/**
 * Step Functions Task target for the `llm_generate` node. A07.3's "回顧生活
 * 紀錄" request is answered by the same schema-validated numbers as the
 * caregiver-facing report (report/compute.ts), not by the LLM — the model
 * never touches this reply, so it can't embellish or infer beyond what's
 * actually in DynamoDB (A07.4). The reply still flows through the normal
 * guardrail_check -> tts_synthesize stages unchanged.
 */
export async function handler(input: LlmStageInput): Promise<LlmGenerateResult> {
  const reportRange = detectReportIntent(input.asrResult.text);
  if (reportRange) {
    const report = await computeReport(new DynamoTable(), input.elderId, reportRange);
    return { replyText: report.voiceSummary, modelId: 'report-query-shortcut', stopReason: 'report_query', inputTokens: 0, outputTokens: 0 };
  }

  const engine = new LlmEngine();
  return engine.generate({
    systemPrompt: input.contextResult.systemPrompt,
    persona: input.contextResult.persona,
    currentUtterance: input.asrResult.text,
    confirmedMemories: input.contextResult.confirmedMemories,
    recentSummary: input.contextResult.recentSummary,
    situationalContext: input.contextResult.situationalContext,
    searchResults: input.contextResult.searchResults,
    conversationHistory: [],
  });
}
