import { Client } from '@opensearch-project/opensearch';
import { AwsSigv4Signer } from '@opensearch-project/opensearch/aws';
import { HEALTH_KNOWLEDGE_INDEX_MAPPING, HEALTH_KNOWLEDGE_INDEX_NAME, MEMORY_VECTORS_INDEX_MAPPING, MEMORY_VECTORS_INDEX_NAME } from './index-mappings.js';

function getEndpoint(): string {
  const endpoint = process.env.OPENSEARCH_ENDPOINT;
  if (!endpoint) throw new Error('OPENSEARCH_ENDPOINT is not configured');
  return endpoint;
}

let cachedClient: Client | null = null;

/**
 * OpenSearch Serverless rejects unsigned requests, so every call has to carry a
 * SigV4 signature — a plain `new Client({ node })` gets 403 regardless of how
 * permissive the IAM policy and data-access policy are.
 *
 * `service: 'aoss'` (not 'es') is what distinguishes Serverless from a managed
 * domain; signing with the wrong service name produces the same 403 as not
 * signing at all. Credentials come from the Lambda execution role via the
 * default provider chain.
 */
export function getOpenSearchClient(): Client {
  if (!cachedClient) {
    const region = process.env.AWS_REGION ?? process.env.AWS_DEFAULT_REGION ?? 'us-west-2';
    cachedClient = new Client({
      ...AwsSigv4Signer({ region, service: 'aoss' }),
      node: getEndpoint(),
    });
  }
  return cachedClient;
}

/** Index lifecycle management (E03.1) — create/update/rebuild the two indices this system depends on. */
export class IndexManager {
  constructor(private readonly client: Client = getOpenSearchClient()) {}

  async createIndex(name: string, mapping: Record<string, unknown>): Promise<void> {
    const exists = await this.client.indices.exists({ index: name });
    if (exists.body) return;
    await this.client.indices.create({ index: name, body: mapping });
  }

  async createHealthKnowledgeIndex(): Promise<void> {
    await this.createIndex(HEALTH_KNOWLEDGE_INDEX_NAME, HEALTH_KNOWLEDGE_INDEX_MAPPING);
  }

  async createMemoryVectorsIndex(): Promise<void> {
    await this.createIndex(MEMORY_VECTORS_INDEX_NAME, MEMORY_VECTORS_INDEX_MAPPING);
  }

  async deleteIndex(name: string): Promise<void> {
    await this.client.indices.delete({ index: name });
  }

  /** Rebuilds an index under a new name and marks it ready for cutover (G03.2). */
  async rebuildIndex(name: string, mapping: Record<string, unknown>): Promise<string> {
    const newName = `${name}-${Date.now()}`;
    await this.createIndex(newName, mapping);
    return newName;
  }
}
