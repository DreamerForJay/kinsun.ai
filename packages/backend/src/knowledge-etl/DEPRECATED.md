# Deprecated knowledge ETL

This TypeScript ingestion path is retained only to avoid deleting historical user code.
It is not the active RAG ingestion implementation and must not be used for new indexing runs.

Use `services/rag-ingestion/` and the scripts under `scripts/rag/` instead. That service owns
allowlist validation, fail-closed JSONL validation, Bedrock document embeddings, staging-index
creation, bulk ingestion, verification, and receipts.

The files in this directory predate the approved chunk corpus. They generate new chunk IDs,
rewrite input text while chunking, and write records one at a time, so they are intentionally
excluded from the active export and runtime call path. `index.ts` exports no legacy symbols;
historical direct imports remain available only for compatibility while callers migrate.
