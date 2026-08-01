# Deprecated reranker

This TypeScript reranker is retained only to avoid deleting historical user code. It is no
longer exported or used by the active health-search route. `index.ts` exports no legacy symbols;
historical direct imports remain available only for compatibility while callers migrate.

Retrieval ranking is owned by agent-runtime and its configured OpenSearch hybrid-search
pipelines. Do not add a second set of hard-coded ranking weights in this package.
