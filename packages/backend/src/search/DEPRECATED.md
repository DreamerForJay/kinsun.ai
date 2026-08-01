# Deprecated TypeScript RAG modules

`client.ts` is the only active module in this directory. It is a thin client for the
agent-runtime retrieval endpoint, and `index.ts` exports only that client.

The following legacy modules are retained only to avoid deleting historical user code and must
not be used by new runtime paths:

- `adapters.ts`
- `answer.ts`
- `embeddings.ts`
- `engine.ts`
- `filter.ts`
- `hybrid.ts`
- `index-management.ts`
- `index-mappings.ts`
- `reformulate.ts`

OpenSearch queries, Bedrock query embeddings, fixed safety filters, hybrid weighting, fallback,
and citation construction now belong to `services/agent-runtime/src/agent_runtime/rag/`. Do not
add direct Bedrock or OpenSearch calls back into the TypeScript API route.

`POST /v1/search/health` keeps its existing `HealthSearchResponse` shape. Until a
citation-aware answer composer is integrated, successful retrievals deliberately return an
ungrounded, non-answer status message instead of exposing a different response shape or joining
chunks into text that could be mistaken for an answer. Consumers that need retrieval chunks use
the agent-runtime contract directly.
