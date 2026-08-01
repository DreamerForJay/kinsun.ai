/**
 * Bedrock model defaults, in one place.
 *
 * These IDs were previously repeated as `?? 'anthropic.claude-...'` literals in
 * six modules, which meant a model reaching end-of-life broke all of them at
 * once and had to be fixed in six places. Every caller now falls back here.
 *
 * The `us.` prefix is an inference profile, not decoration: current Claude
 * models reject on-demand invocation by bare model ID with
 *   "Invocation of model ID ... with on-demand throughput isn't supported.
 *    Retry your request with the ID or ARN of an inference profile."
 * so dropping the prefix makes every LLM call fail.
 *
 * Deployments should set BEDROCK_MODEL_ID / BEDROCK_EMBEDDING_MODEL_ID
 * explicitly (infrastructure/lib/elderly-care-stack.ts does) so the version in
 * use is recorded rather than implied; these values are the local-dev fallback.
 */

/** Verified callable in us-west-2 via the Converse API. */
export const DEFAULT_BEDROCK_MODEL_ID = 'us.anthropic.claude-sonnet-4-5-20250929-v1:0';

/**
 * Titan Text Embeddings V2 — 1024 dimensions, which must stay equal to the
 * knn_vector dimension in search/index-mappings.ts. Changing the embedding
 * model requires reindexing, not just editing this constant.
 */
export const DEFAULT_BEDROCK_EMBEDDING_MODEL_ID = 'amazon.titan-embed-text-v2:0';

/** Resolves the chat/completion model: env override first, then the default. */
export function resolveModelId(): string {
  return process.env.BEDROCK_MODEL_ID ?? DEFAULT_BEDROCK_MODEL_ID;
}

/** Resolves the embedding model: env override first, then the default. */
export function resolveEmbeddingModelId(): string {
  return process.env.BEDROCK_EMBEDDING_MODEL_ID ?? DEFAULT_BEDROCK_EMBEDDING_MODEL_ID;
}
