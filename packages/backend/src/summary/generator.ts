import { BedrockRuntimeClient, ConverseCommand } from '@aws-sdk/client-bedrock-runtime';
import { ulid } from 'ulid';
import type { EventRecord, SummaryContent, SummaryRecord } from '@elderly-care/shared';
import { computeTtlEpochSeconds, DynamoTable, Keys, RETENTION_DAYS } from '../db/index.js';
import { resolveModelId } from '../llm/models.js';
import { prioritizeEvents } from './prioritize.js';

export interface SummaryGenerationAdapter {
  generate(elderId: string, date: string, events: EventRecord[]): Promise<SummaryContent>;
}

/** The subset of DynamoTable SummaryGenerator needs — lets tests substitute an in-memory fake. */
export interface SummaryDataStore {
  queryByPk<T>(pk: string, skPrefix?: string, limit?: number): Promise<T[]>;
  putItem<T extends object>(item: T): Promise<void>;
}

const SUMMARY_SYSTEM_PROMPT = `你是一個為長者生活事件產生每日摘要的系統。
只能根據提供的事件清單撰寫摘要，涵蓋飲食、活動、睡眠、用藥陳述與重要事件。
絕對不可以新增事件清單中不存在的診斷、醫療判斷或推測。
用藥陳述只能照事件中的原始描述呈現，不得判斷是否遵從醫囑或評估藥效。
只回傳 JSON 物件，格式為 { overview, meals: string[], activities: string[], sleep: string|null, medicationStatements: string[], importantEvents: string[], emotionalState: string|null }。`;

/** Real summary generation via Amazon Bedrock (B02.1-B02.4). */
export class BedrockSummaryAdapter implements SummaryGenerationAdapter {
  constructor(
    private readonly client: BedrockRuntimeClient = new BedrockRuntimeClient({}),
    private readonly modelId: string = resolveModelId(),
  ) {}

  async generate(elderId: string, date: string, events: EventRecord[]): Promise<SummaryContent> {
    const eventLines = events
      .map((e) => `- [${e.eventType}/${e.reviewStatus}] ${e.content} (event_id: ${e.eventId})`)
      .join('\n');
    const response = await this.client.send(
      new ConverseCommand({
        modelId: this.modelId,
        system: [{ text: SUMMARY_SYSTEM_PROMPT }],
        messages: [
          { role: 'user', content: [{ text: `Elder ID: ${elderId}\n日期: ${date}\n\n事件清單：\n${eventLines || '(無事件)'}` }] },
        ],
        inferenceConfig: { maxTokens: 1024, temperature: 0.2 },
      }),
    );
    const text = response.output?.message?.content?.map((c) => c.text ?? '').join('') ?? '{}';
    try {
      return JSON.parse(text) as SummaryContent;
    } catch {
      return {
        overview: '摘要產生失敗',
        meals: [],
        activities: [],
        sleep: null,
        medicationStatements: [],
        importantEvents: [],
        emotionalState: null,
      };
    }
  }
}

/**
 * SummaryGenerator (B02) — fetches one elder's events for a date, prioritizes
 * caregiver-confirmed data, generates the narrative via the adapter, and
 * persists a SummaryRecord whose sourceEventIds are drawn *only* from the
 * events actually fed to the adapter. That construction is what guarantees
 * Property 8 (every summary traces back to a real, existing event) —
 * sourceEventIds can never contain an ID that wasn't in the input set,
 * because it's built by mapping that exact set, not by parsing the model's
 * free-text output.
 */
export class SummaryGenerator {
  constructor(
    private readonly table: SummaryDataStore = new DynamoTable(),
    private readonly adapter: SummaryGenerationAdapter = new BedrockSummaryAdapter(),
  ) {}

  async generateDailySummary(elderId: string, date: string): Promise<SummaryRecord> {
    const events = await this.table.queryByPk<EventRecord>(Keys.elderPk(elderId), `EVENT#${date}`);
    const prioritized = prioritizeEvents(events);
    const content = await this.adapter.generate(elderId, date, prioritized);

    const record: SummaryRecord = {
      PK: Keys.elderPk(elderId),
      SK: Keys.summarySk(date),
      summaryId: `sum_${ulid()}`,
      elderId,
      date,
      content,
      sourceEventIds: prioritized.map((e) => e.eventId),
      generatedAt: new Date().toISOString(),
      version: 1,
      ttl: computeTtlEpochSeconds(RETENTION_DAYS.summary),
      status: 'draft',
      publishedAt: null,
      publishedBy: null,
    };

    await this.table.putItem(record);
    return record;
  }
}
