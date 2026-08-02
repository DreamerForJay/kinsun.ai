# RAG Ingestion Service

Offline, staging-only ingestion for the approved kinsun.ai RAG chunk set. The
service validates the complete allowlisted dataset before any external call,
embeds documents with Bedrock Cohere Embed v4, creates documents with
`chunk_id` as OpenSearch `_id`, bulk ingests into a fresh staging index, and
verifies count, duplicate IDs, and every vector dimension before moving the
staging alias.

## Safety boundaries

- Only direct `*.jsonl` children of the configured approved directory are read.
- A path containing `pending-revalidation` is always rejected.
- Unknown, missing, or duplicate `chunk_id` values fail the complete run.
- `text` and `embedding_text` are hashed byte-for-byte as UTF-8 and compared
  with the Allowlist; neither field is modified.
- `RAG_ALLOWLIST_EXPECTED_SHA256` is always required and compared in constant
  time with the complete loaded Allowlist before Bedrock or OpenSearch starts.
- In staging only, `RAG_REQUIRE_OWNER_SIGNATURE=false` permits the supplied
  `NOT_SIGNED` owner-signature-pending Allowlist under the narrow
  `UNSIGNED_DEVELOPMENT_OVERRIDE`. It does not permit revoked/rejected state,
  malformed counts, hash mismatches, or chunks outside the Allowlist.
- Production context never uses the unsigned override. It requires an
  effective, formally signed, production-approved Allowlist and an enabled
  production switch; this first release still refuses every non-staging target.
- The current supplied Allowlist records Human Review as `NOT_COMPLETED`; the
  service carries that state into receipts and never upgrades it.
- Embedding artifacts default to the OS temp directory at
  `kinsun-rag/embeddings.jsonl`. Any artifact path inside the repository is
  rejected. Receipts contain counts and governance state, never vectors or
  source text.
- A `VERIFIED_PENDING_ALIAS` receipt is durably written before alias cutover.
  If alias activation or the final `COMPLETED` receipt fails, the new index is
  removed and the prior single-target alias is restored when one existed.
- Index and alias names must explicitly contain `staging`; production-like
  names and non-staging mode are rejected.
- The staging collection uses OpenSearch Serverless NextGen `VECTORSEARCH`.
  Its ANN mapping is fail-closed to `knn_vector` / 1024 dimensions /
  `cosinesimil` / HNSW. NextGen selects the engine, so any `method.engine`
  configuration is rejected before an OpenSearch request.
- Search pipelines are reconciled before index creation. All existing pipeline
  definitions must match before any missing pipeline is written, and all
  acknowledged writes share one 0-to-60-second visibility window. A pipeline
  that remains invisible is retained for exact-match reconciliation on the
  next run; it is not deleted into an eventual-consistency tombstone.
- Serverless rejects the `wait_for` refresh policy, so bulk create does not
  request it. Post-ingest verification instead polls the document count over
  the same 0-to-60-second window; a count above the expected total is not a
  visibility delay and fails immediately. Requests use a 120-second timeout
  because a full staging bulk has been measured at roughly 24 seconds.

## Configuration

The CLI reads these checked-in files from `config/rag/` (or `--config-dir`):

- `embedding.yaml`
- `opensearch-index-v1.json`
- `hybrid-natural-language.json`
- `hybrid-legal.json`
- `staging-filters.yaml`
- `smoke-test.yaml`

Environment variables override config values. Required variables depend on
the operation: `AWS_REGION`, `BEDROCK_EMBEDDING_MODEL_ID`,
`BEDROCK_EMBEDDING_DIMENSION`, `OPENSEARCH_HOST`, `OPENSEARCH_INDEX`,
`OPENSEARCH_ALIAS`, `RAG_ALLOWLIST_PATH`, `RAG_CHUNKS_DIR`, and `RAG_MODE`.
Before any AWS operation, `RAG_ALLOWLIST_EXPECTED_SHA256` must also contain an
independently supplied SHA-256 that exactly matches the loaded Allowlist; the
manifest cannot attest itself. `RAG_REQUIRE_OWNER_SIGNATURE` defaults to
`false` for staging development, while `RAG_PRODUCTION_ENABLED` defaults to
`false` and cannot turn this staging-only release into a production writer.
`RAG_EMBEDDINGS_PATH` and `RAG_RECEIPT_PATH` are optional. AWS credentials use
the normal boto3 credential chain and must never be committed.

The individual config paths can be overridden with
`RAG_EMBEDDING_CONFIG_PATH`, `RAG_OPENSEARCH_INDEX_CONFIG_PATH`,
`RAG_HYBRID_NATURAL_CONFIG_PATH`, `RAG_HYBRID_LEGAL_CONFIG_PATH`, and
`RAG_STAGING_FILTERS_CONFIG_PATH`. `RAG_SMOKE_CONFIG_PATH` selects the two
end-to-end smoke requests, and `AGENT_RUNTIME_BASE_URL` supplies the reachable
runtime origin.

## Commands

From the repository root, run the required staging sequence:

```powershell
python scripts/rag/validate_allowlist.py
python scripts/rag/create_index.py
python scripts/rag/generate_embeddings.py
python scripts/rag/ingest.py
python scripts/rag/verify_index.py
python scripts/rag/smoke_test.py
```

The thin scripts delegate to these service subcommands:

```powershell
uv run --project services/rag-ingestion python -m rag_ingestion.cli validate-allowlist
uv run --project services/rag-ingestion python -m rag_ingestion.cli create-index
uv run --project services/rag-ingestion python -m rag_ingestion.cli generate-embeddings
uv run --project services/rag-ingestion python -m rag_ingestion.cli ingest
uv run --project services/rag-ingestion python -m rag_ingestion.cli verify-index
uv run --project services/rag-ingestion python -m rag_ingestion.cli smoke-test
```

For diagnostics outside that required six-step sequence, this read-only command
loads the same staging configuration and governance gate, then reads each
configured pipeline exactly once. It never creates, updates, deletes, or reads
an index, and reports only each pipeline name, visibility, and configuration
match state:

```powershell
python scripts/rag/inspect_pipelines.py
# or
uv run --project services/rag-ingestion python -m rag_ingestion.cli inspect-pipelines
```

Adding or editing an approved chunk means recomputing every hash the Allowlist
declares, which is the step most likely to go wrong by hand. This reports what
the approved JSONL files imply, and writes the manifest only with `--write`:

```powershell
python scripts/rag/rebuild_allowlist.py
python scripts/rag/rebuild_allowlist.py --write
```

It recomputes `text_sha256` and `embedding_text_sha256`, refreshes per-source
and total counts, and reports added, removed, and rehashed chunks. It never
touches governance: manifest status, owner risk acceptance, human review, and
production status are copied verbatim, and a chunk the manifest has not seen
before inherits `review_status=needs_review`, `human_source_review=NOT_COMPLETED`
and `production_gate=BLOCKED` rather than the state of its neighbours. A chunk
whose `source_id` has no reviewed `sources[]` entry is refused, because
`source_number` ties a source to the human review catalogue and a script must
not invent one.

Reformatting alone is reported as `UNCHANGED`; rewriting then would change the
Allowlist SHA-256 without any chunk differing, invalidating the attested
`RAG_ALLOWLIST_EXPECTED_SHA256` for nothing. When chunks really did change,
place the new SHA-256 into that variable by hand from an independently trusted
record, then rebuild the index: ingestion writes the complete approved set and
verifies an exact count, so it is a full rebuild rather than an append.

Every command prints a JSON summary without chunk text or vectors. Structural
validation can report `VALID` while `execution_allowed` is false; every command
that could contact AWS independently enforces the governance gate. Successful
summaries and every failure after governance evaluation include `governance_status` and
`production_approved`. Receipts persist those fields under `governance`; the
unsigned staging override records `UNSIGNED_DEVELOPMENT_OVERRIDE` and `false`.
The Bedrock, index, and bulk adapters are internal implementation boundaries;
operators must use the six repository scripts so the Allowlist and SHA gates run first.

`smoke-test` first verifies the alias, configured search pipelines, citation
identity, and mandatory `current_status=current` /
`stop_normal_rag=false` filters. It then POSTs the configured positive and
no-data cases to the Agent Runtime retrieval endpoint. A pass requires a
standard success envelope, three to five fully cited chunks for the positive
case, and `NO_DATA` with an empty result set and explicit fallback for the
negative case. A missing or unreachable runtime is a failed smoke test.

## Tests

Tests inject fake Bedrock and OpenSearch clients and make no network calls:

```powershell
cd services/rag-ingestion
uv sync --extra test --extra dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
