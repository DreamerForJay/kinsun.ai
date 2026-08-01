import { BedrockRuntimeClient, ConverseCommand } from '@aws-sdk/client-bedrock-runtime';
import type { ConversationRecord, ExtractedEvent } from '@elderly-care/shared';
import { isConfidenceAcceptable } from '../asr/confidence.js';
import { resolveModelId } from '../llm/models.js';
import { validateExtractedEvent } from './schema.js';

export const EVENT_EXTRACTION_CONFIDENCE_THRESHOLD = 0.7;

export interface ExtractionOutcome {
  valid: ExtractedEvent[];
  rejected: { raw: unknown; errors: string[] }[];
}

export interface ExtractionAdapter {
  /** Returns raw, not-yet-validated candidate event objects extracted from the conversation. */
  extractRaw(conversation: ConversationRecord): Promise<unknown[]>;
}

const EXTRACTION_SYSTEM_PROMPT = `你是一個從長者對話中擷取結構化生活事件的系統。
從對話中找出飲食(meal)、活動(activity)、睡眠(sleep)、用藥陳述(medication_statement)、情緒(emotion)、重要事件(important_event)。

重要規則：
- 用藥相關內容只能記錄長者的「原始陳述」（例如「我今天有吃血壓藥」），絕對不可以推論用藥遵從度、藥效或身體反應。
- 每筆事件必須包含：eventId、elderId、eventType、content、originalUtterance（原始逐字稿片段）、eventDate、confidence（0-1）、sourceConversationId、reviewStatus、createdAt、metadata。
- 不確定或含糊的陳述，confidence 給低分（< 0.7）。
- 只回傳 JSON 陣列，不要有其他文字。`;

/** Real extraction via Amazon Bedrock (B01.1). */
export class BedrockExtractionAdapter implements ExtractionAdapter {
  constructor(
    private readonly client: BedrockRuntimeClient = new BedrockRuntimeClient({}),
    private readonly modelId: string = resolveModelId(),
  ) {}

  async extractRaw(conversation: ConversationRecord): Promise<unknown[]> {
    const transcript = conversation.turns.map((t) => `${t.role}: ${t.content}`).join('\n');
    const response = await this.client.send(
      new ConverseCommand({
        modelId: this.modelId,
        system: [{ text: EXTRACTION_SYSTEM_PROMPT }],
        messages: [
          {
            role: 'user',
            content: [
              {
                text: `對話 ID: ${conversation.conversationId}\nElder ID: ${conversation.elderId}\n\n對話內容：\n${transcript}`,
              },
            ],
          },
        ],
        inferenceConfig: { maxTokens: 2048, temperature: 0.1 },
      }),
    );
    const text = response.output?.message?.content?.map((c) => c.text ?? '').join('') ?? '[]';
    try {
      const parsed = JSON.parse(text);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }
}

/**
 * EventExtractor (B01) — every candidate must pass schema validation
 * (Property 6/7) before it counts as "valid"; anything that fails is
 * returned separately in `rejected` and must never be persisted. A
 * candidate that passes schema validation but falls below the confidence
 * threshold is force-downgraded to needs_review regardless of what the
 * model claimed (B01.5), so a confident-sounding but low-confidence
 * extraction can't skip caregiver review.
 */
export class EventExtractor {
  constructor(
    private readonly adapter: ExtractionAdapter,
    private readonly confidenceThreshold: number = EVENT_EXTRACTION_CONFIDENCE_THRESHOLD,
  ) {}

  async extract(conversation: ConversationRecord): Promise<ExtractionOutcome> {
    const rawCandidates = await this.adapter.extractRaw(conversation);
    const valid: ExtractedEvent[] = [];
    const rejected: { raw: unknown; errors: string[] }[] = [];

    for (const candidate of rawCandidates) {
      const result = validateExtractedEvent(candidate);
      if (!result.success) {
        rejected.push({ raw: candidate, errors: result.errors });
        continue;
      }
      const event = result.data;
      const reviewStatus = isConfidenceAcceptable(event.confidence, this.confidenceThreshold)
        ? event.reviewStatus
        : 'needs_review';
      valid.push({ ...event, reviewStatus });
    }

    return { valid, rejected };
  }
}
