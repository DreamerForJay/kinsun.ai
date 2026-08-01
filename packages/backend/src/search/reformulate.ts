import { BedrockRuntimeClient, ConverseCommand } from '@aws-sdk/client-bedrock-runtime';
import { resolveModelId } from '../llm/models.js';

export interface QueryReformulator {
  reformulate(originalQuestion: string): Promise<string>;
}

const REFORMULATE_SYSTEM_PROMPT = `你是一個將長者口語問題轉換為適合檢索的查詢的系統。
規則：
- 保留原始問題中的關鍵醫療條件、限定範圍與數量詞，絕不可改變或省略
- 移除口語贅字（例如「那個」「就是說」「你知道嗎」）
- 只回傳轉換後的查詢文字，不要有其他說明`;

/** Real reformulation via Amazon Bedrock (E01.1, E01.2). */
export class BedrockQueryReformulator implements QueryReformulator {
  constructor(
    private readonly client: BedrockRuntimeClient = new BedrockRuntimeClient({}),
    private readonly modelId: string = resolveModelId(),
  ) {}

  async reformulate(originalQuestion: string): Promise<string> {
    try {
      const response = await this.client.send(
        new ConverseCommand({
          modelId: this.modelId,
          system: [{ text: REFORMULATE_SYSTEM_PROMPT }],
          messages: [{ role: 'user', content: [{ text: originalQuestion }] }],
          inferenceConfig: { maxTokens: 200, temperature: 0 },
        }),
      );
      const text = response.output?.message?.content?.map((c) => c.text ?? '').join('').trim();
      return text || originalQuestion;
    } catch {
      // Reformulation is an optimization, not a correctness requirement —
      // falling back to the verbatim question keeps search working.
      return originalQuestion;
    }
  }
}
