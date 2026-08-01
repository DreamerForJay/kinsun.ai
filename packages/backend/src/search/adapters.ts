import { Client } from '@opensearch-project/opensearch';
import { BedrockRuntimeClient } from '@aws-sdk/client-bedrock-runtime';
import type { DocumentMetadata, MetadataFilter, SearchResult } from '@elderly-care/shared';
import { resolveEmbeddingModelId } from '../llm/models.js';
import { embedText } from './embeddings.js';
import { HEALTH_KNOWLEDGE_INDEX_NAME } from './index-mappings.js';
import { getOpenSearchClient } from './index-management.js';

interface OpenSearchHit {
  _id: string;
  _score: number;
  _source: {
    document_id: string;
    content: string;
    source_agency: string;
    document_title: string;
    effective_date: string;
    expiry_date: string | null;
    service_type: string;
    region: string;
    risk_level: string;
    review_status: DocumentMetadata['reviewStatus'];
    version: string;
  };
}

function toSearchResult(hit: OpenSearchHit, bm25Score: number, vectorScore: number): SearchResult {
  const s = hit._source;
  return {
    chunkId: hit._id,
    documentId: s.document_id,
    content: s.content,
    sourceAgency: s.source_agency,
    documentTitle: s.document_title,
    publishDate: s.effective_date,
    bm25Score,
    vectorScore,
    combinedScore: bm25Score + vectorScore,
    metadata: {
      sourceAgency: s.source_agency,
      serviceType: s.service_type,
      region: s.region,
      effectiveDate: s.effective_date,
      expiryDate: s.expiry_date,
      riskLevel: s.risk_level,
      reviewStatus: s.review_status,
      version: s.version,
    },
  };
}

function buildFilterClauses(filter: MetadataFilter): Record<string, unknown>[] {
  const clauses: Record<string, unknown>[] = [{ term: { review_status: filter.reviewStatus } }];
  if (filter.sourceAgency?.length) clauses.push({ terms: { source_agency: filter.sourceAgency } });
  if (filter.serviceType?.length) clauses.push({ terms: { service_type: filter.serviceType } });
  if (filter.region?.length) clauses.push({ terms: { region: filter.region } });
  if (filter.riskLevel?.length) clauses.push({ terms: { risk_level: filter.riskLevel } });
  if (filter.effectiveDateAfter) clauses.push({ range: { effective_date: { gte: filter.effectiveDateAfter } } });
  return clauses;
}

export interface Bm25SearchAdapter {
  search(query: string, filter: MetadataFilter, topK: number): Promise<SearchResult[]>;
}

/** BM25 keyword search over the health-knowledge index (E03.1). */
export class OpenSearchBm25Adapter implements Bm25SearchAdapter {
  constructor(private readonly client: Client = getOpenSearchClient()) {}

  async search(query: string, filter: MetadataFilter, topK: number): Promise<SearchResult[]> {
    const response = await this.client.search({
      index: HEALTH_KNOWLEDGE_INDEX_NAME,
      body: {
        size: topK,
        query: { bool: { must: [{ match: { content: query } }], filter: buildFilterClauses(filter) } },
      },
    });
    const hits = (response.body.hits?.hits ?? []) as OpenSearchHit[];
    return hits.map((hit) => toSearchResult(hit, hit._score, 0));
  }
}

export interface VectorSearchAdapter {
  search(query: string, filter: MetadataFilter, topK: number): Promise<SearchResult[]>;
}

/** Vector KNN semantic search using Bedrock embeddings (E03.1). */
export class OpenSearchVectorAdapter implements VectorSearchAdapter {
  constructor(
    private readonly client: Client = getOpenSearchClient(),
    private readonly bedrockClient: BedrockRuntimeClient = new BedrockRuntimeClient({}),
    private readonly embeddingModelId: string = resolveEmbeddingModelId(),
  ) {}

  async search(query: string, filter: MetadataFilter, topK: number): Promise<SearchResult[]> {
    const vector = await embedText(this.bedrockClient, query, this.embeddingModelId);
    const response = await this.client.search({
      index: HEALTH_KNOWLEDGE_INDEX_NAME,
      body: {
        size: topK,
        query: {
          bool: {
            must: [{ knn: { content_vector: { vector, k: topK } } }],
            filter: buildFilterClauses(filter),
          },
        },
      },
    });
    const hits = (response.body.hits?.hits ?? []) as OpenSearchHit[];
    return hits.map((hit) => toSearchResult(hit, 0, hit._score));
  }
}
