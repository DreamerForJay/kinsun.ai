import { BedrockRuntimeClient, ConverseCommand } from '@aws-sdk/client-bedrock-runtime';
import type { CandidateMemory, ConversationRecord } from '@elderly-care/shared';
import { resolveModelId } from '../llm/models.js';
import { validateCandidateMemory } from './schema.js';

export interface CandidateGenerationOutcome {
  valid: CandidateMemory[];
  rejected: { raw: unknown; errors: string[] }[];
}

export interface MemoryGenerationAdapter {
  generateRaw(conversation: ConversationRecord): Promise<unknown[]>;
}

const GENERATION_SYSTEM_PROMPT = `你是一個從長者對話中識別「值得長期記住」資訊的系統。

只能為以下三類資訊產生候選記憶：
1. 穩定偏好（例如：喜歡喝烏龍茶、不吃辣）
2. 重要關係（例如：大兒子叫阿明，住台中）
3. 固定作息（例如：習慣早上六點起床散步）

絕對不可以：
- 將閒聊內容（例如天氣、心情抒發）當作候選記憶
- 將敏感推測（例如推論健康狀況、心理狀態）當作候選記憶
- 憑空捏造對話中沒有明確提到的資訊

每筆候選記憶必須包含：memoryId、elderId、category、content、sourceConversationId、confidence（0-1）、createdAt、status（固定為 "pending"）。
只回傳 JSON 陣列，不要有其他文字。若對話中沒有符合條件的資訊，回傳空陣列。`;

/** Real candidate generation via Amazon Bedrock (D01.1). */
export class BedrockMemoryGenerationAdapter implements MemoryGenerationAdapter {
  constructor(
    private readonly client: BedrockRuntimeClient = new BedrockRuntimeClient({}),
    private readonly modelId: string = resolveModelId(),
  ) {}

  async generateRaw(conversation: ConversationRecord): Promise<unknown[]> {
    const transcript = conversation.turns.map((t) => `${t.role}: ${t.content}`).join('\n');
    const response = await this.client.send(
      new ConverseCommand({
        modelId: this.modelId,
        system: [{ text: GENERATION_SYSTEM_PROMPT }],
        messages: [
          {
            role: 'user',
            content: [{ text: `對話 ID: ${conversation.conversationId}\nElder ID: ${conversation.elderId}\n\n對話內容：\n${transcript}` }],
          },
        ],
        inferenceConfig: { maxTokens: 1024, temperature: 0.1 },
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
 * Generates candidate memories (D01). Every candidate the model proposes
 * still passes through validateCandidateMemory before it's trusted with
 * status/id semantics — chit-chat filtering happens in the prompt (a soft
 * guarantee), but the required-field gate (Property 7) is a hard one
 * enforced here regardless of what the model returns.
 */
export class MemoryCandidateGenerator {
  constructor(private readonly adapter: MemoryGenerationAdapter) {}

  async generateCandidates(conversation: ConversationRecord): Promise<CandidateGenerationOutcome> {
    const rawCandidates = await this.adapter.generateRaw(conversation);
    const valid: CandidateMemory[] = [];
    const rejected: { raw: unknown; errors: string[] }[] = [];

    for (const candidate of rawCandidates) {
      const result = validateCandidateMemory(candidate);
      if (!result.success) {
        rejected.push({ raw: candidate, errors: result.errors });
        continue;
      }
      valid.push(result.data);
    }

    return { valid, rejected };
  }
}
