import { BedrockRuntimeClient, ConverseCommand, type Message } from '@aws-sdk/client-bedrock-runtime';
import { buildUserMessage } from './message-builder.js';
import { resolveModelId } from './models.js';
import type { LlmGenerateRequest, LlmGenerateResult } from './types.js';

const DEFAULT_MODEL_ID = resolveModelId();

/** LLM Engine (A03, A04) — Amazon Bedrock Converse API wrapper around Claude. */
export class LlmEngine {
  constructor(
    private readonly client: BedrockRuntimeClient = new BedrockRuntimeClient({}),
    private readonly modelId: string = DEFAULT_MODEL_ID,
  ) {}

  async generate(request: LlmGenerateRequest): Promise<LlmGenerateResult> {
    const historyMessages: Message[] = request.conversationHistory.map((turn) => ({
      role: turn.role === 'elder' ? 'user' : 'assistant',
      content: [{ text: turn.content }],
    }));

    const messages: Message[] = [
      ...historyMessages,
      { role: 'user', content: [{ text: buildUserMessage(request) }] },
    ];

    const response = await this.client.send(
      new ConverseCommand({
        modelId: this.modelId,
        system: [{ text: request.systemPrompt }],
        messages,
        inferenceConfig: { maxTokens: 512, temperature: 0.4 },
      }),
    );

    const replyText =
      response.output?.message?.content
        ?.map((block) => block.text ?? '')
        .join('')
        .trim() ?? '';

    return {
      replyText,
      modelId: this.modelId,
      stopReason: response.stopReason ?? null,
      inputTokens: response.usage?.inputTokens ?? 0,
      outputTokens: response.usage?.outputTokens ?? 0,
    };
  }
}
