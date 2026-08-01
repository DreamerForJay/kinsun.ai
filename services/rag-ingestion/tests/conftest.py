from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def synthetic_chunk(chunk_id: str = "synthetic_source_chunk_001") -> dict[str, Any]:
    text = "Synthetic public-care reference text."
    embedding_text = "Synthetic public-care reference text for retrieval."
    return {
        "chunk_id": chunk_id,
        "chunk_index": 1,
        "source_id": "synthetic_source",
        "document_title": "Synthetic Care Guide",
        "section": "Safe information",
        "page_start": 1,
        "page_end": 1,
        "source_locator": "page 1",
        "text": text,
        "embedding_text": embedding_text,
        "metadata": {
            "official_source_url": "https://example.invalid/synthetic-guide",
            "current_status": "current",
            "stop_normal_rag": False,
            "risk_level": "low",
            "requires_human_review": False,
            "allowed_audiences": ["elder"],
            "allowed_purposes": ["general_information"],
            "source_version": "synthetic-v1",
            "text_sha256": sha256_text(text),
            "embedding_text_sha256": sha256_text(embedding_text),
        },
    }


def write_dataset(
    root: Path,
    *,
    chunks: list[dict[str, Any]] | None = None,
    effective: bool = True,
    omit_entry_source_id: bool = False,
) -> tuple[Path, Path]:
    records = chunks or [synthetic_chunk()]
    chunks_dir = root / "approved"
    chunks_dir.mkdir(parents=True)
    with (chunks_dir / "synthetic.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for chunk in records:
            handle.write(json.dumps(chunk, ensure_ascii=False))
            handle.write("\n")

    entries = []
    for chunk in records:
        entry = {
            "source_number": 1,
            "source_title": "Synthetic Care Guide",
            "source_version": "synthetic-v1",
            "chunk_id": chunk["chunk_id"],
            "chunk_index": chunk["chunk_index"],
            "text_sha256": sha256_text(chunk.get("text", "")),
            "embedding_text_sha256": sha256_text(chunk.get("embedding_text", "")),
        }
        if not omit_entry_source_id:
            entry["source_id"] = "synthetic_source"
        entries.append(entry)
    manifest = {
        "schema_version": "test-v1",
        "status": (
            "EFFECTIVE"
            if effective
            else "DRAFT_FIXED_HASH_NOT_EFFECTIVE_UNTIL_PROJECT_OWNER_SIGNATURE"
        ),
        "source_count": 1,
        "chunk_count": len(entries),
        "sources": [
            {
                "source_number": 1,
                "source_id": "synthetic_source",
                "chunk_count": len(entries),
            }
        ],
        "entries": entries,
        "project_owner_risk_acceptance": "SIGNED" if effective else "NOT_SIGNED",
        "human_source_review": "NOT_COMPLETED",
        "production_status": "BLOCKED",
    }
    manifest_path = root / "allowlist.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return manifest_path, chunks_dir


@pytest.fixture
def dataset(tmp_path: Path) -> tuple[Path, Path]:
    return write_dataset(tmp_path)
