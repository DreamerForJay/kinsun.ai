import { BedrockRuntimeClient, InvokeModelCommand } from '@aws-sdk/client-bedrock-runtime';
import { resolveEmbeddingModelId } from '../llm/models.js';

const DEFAULT_EMBEDDING_MODEL_ID = resolveEmbeddingModelId();

/** Shared embedding call — used by both vector search (query time) and the knowledge ETL pipeline (index time). */
export async function embedText(
  client: BedrockRuntimeClient,
  text: string,
  modelId: string = DEFAULT_EMBEDDING_MODEL_ID,
): Promise<number[]> {
  const response = await client.send(
    new InvokeModelCommand({
      modelId,
      contentType: 'application/json',
      body: JSON.stringify({ inputText: text }),
    }),
  );
  const payload = JSON.parse(Buffer.from(response.body).toString('utf-8'));
  return payload.embedding as number[];
}
