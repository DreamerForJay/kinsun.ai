from __future__ import annotations

from pathlib import Path

from rag_ingestion.allowlist import UNSIGNED_DEVELOPMENT_OVERRIDE, load_allowlist
from rag_ingestion.bulk_ingester import build_index_document
from rag_ingestion.chunk_loader import load_allowlisted_chunks
from rag_ingestion.validator import validate_chunks


def test_current_approved_dataset_matches_allowlist_and_normalizes_filters() -> None:
    repository_root = Path(__file__).resolve().parents[4]
    allowlist = load_allowlist(
        repository_root
        / "data"
        / "rag-manifest"
        / "AI_Reviewed_Embedding_Staging_Allowlist_v002.json"
    )
    loaded = load_allowlisted_chunks(
        repository_root / "data" / "rag-chunks" / "approved", allowlist
    )

    result = validate_chunks(loaded, allowlist)
    documents = [build_index_document(chunk, [0.0] * 1024) for chunk in result.chunks]

    assert result.source_count == 6
    assert result.chunk_count == 262
    assert allowlist.governance.effective is False
    assert allowlist.governance.project_owner_risk_acceptance == "NOT_SIGNED"
    decision = allowlist.execution_governance(
        allowlist.sha256,
        mode="staging",
        require_owner_signature=False,
        production_enabled=False,
    )
    assert decision.execution_allowed is True
    assert decision.governance_status == UNSIGNED_DEVELOPMENT_OVERRIDE
    assert decision.production_approved is False
    assert all(isinstance(document["stop_normal_rag"], bool) for document in documents)
    assert sum(document["stop_normal_rag"] for document in documents) == 7
    assert all(document["current_status"] for document in documents)
    documents_by_id = {document["chunk_id"]: document for document in documents}
    first_manual_chunk = documents_by_id["mohw_a_unit_case_manager_manual_20230719_chunk_001"]
    assert first_manual_chunk["page_start"] == 4
    assert first_manual_chunk["page_end"] == 4
