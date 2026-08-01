import { BedrockRuntimeClient, ConverseCommand } from '@aws-sdk/client-bedrock-runtime';
import type { HealthSearchResponse } from '@elderly-care/shared';
import type { PersonaContext, RankedResult } from '@elderly-care/shared';
import { resolveModelId } from '../llm/models.js';
import { Reranker } from '../reranker/reranker.js';
import type { SearchEngine } from './engine.js';

const DISCLAIMER = '僅供參考，不作為醫療診斷依據';
const NO_RESULTS_ANSWER = '目前查無相關的衛教資訊，建議您諮詢醫師或照護者。';

const ANSWER_SYSTEM_PROMPT = `你是一個根據衛教文件回答長者健康問題的系統。
規則：
- 只能根據提供的文件內容回答，不可以自行補充或推測未提及的資訊
- 回答中必須提及資訊來源（文件名稱／發布機關）
- 如果提供的文件不足以回答問題，必須明確說「目前查無相關資訊」，絕不可虛構答案
- 語氣溫和、簡潔，適合對長者說話`;

export interface HealthAnswerDeps {
  searchEngine: SearchEngine;
  reranker?: Reranker;
  llmClient?: BedrockRuntimeClient;
  modelId?: string;
  topN?: number;
}

/**
 * HealthAnswerGenerator (E05) — search -> rerank -> top-N -> grounded LLM
 * answer, always attaching source citations and the medical disclaimer.
 * When there are no valid search results at all, skips the LLM call
 * entirely and returns the fixed "don't know" answer (E01.4/E05.2) rather
 * than letting the model improvise without grounding.
 */
export class HealthAnswerGenerator {
  private readonly reranker: Reranker;
  private readonly llmClient: BedrockRuntimeClient;
  private readonly modelId: string;
  private readonly topN: number;

  constructor(private readonly deps: HealthAnswerDeps) {
    this.reranker = deps.reranker ?? new Reranker();
    this.llmClient = deps.llmClient ?? new BedrockRuntimeClient({});
    this.modelId = deps.modelId ?? resolveModelId();
    this.topN = deps.topN ?? 5;
  }

  async answer(question: string, persona?: PersonaContext): Promise<HealthSearchResponse> {
    const { results } = await this.deps.searchEngine.search(question);

    if (results.length === 0) {
      return { answer: NO_RESULTS_ANSWER, sources: [], disclaimer: DISCLAIMER, grounded: false };
    }

    const ranked = this.reranker.rerank(question, results, persona);
    const topResults = this.reranker.topN(ranked, this.topN);

    const answerText = await this.generateGroundedAnswer(question, topResults);

    return {
      answer: answerText,
      sources: topResults.map((r) => ({ documentTitle: r.documentTitle, sourceAgency: r.sourceAgency, chunkId: r.chunkId })),
      disclaimer: DISCLAIMER,
      grounded: true,
    };
  }

  private async generateGroundedAnswer(question: string, results: RankedResult[]): Promise<string> {
    const context = results
      .map((r) => `[來源: ${r.documentTitle}／${r.sourceAgency}]\n${r.content}`)
      .join('\n\n');

    const response = await this.llmClient.send(
      new ConverseCommand({
        modelId: this.modelId,
        system: [{ text: ANSWER_SYSTEM_PROMPT }],
        messages: [{ role: 'user', content: [{ text: `問題：${question}\n\n參考文件：\n${context}` }] }],
        inferenceConfig: { maxTokens: 512, temperature: 0.2 },
      }),
    );

    return response.output?.message?.content?.map((c) => c.text ?? '').join('').trim() || NO_RESULTS_ANSWER;
  }
}
