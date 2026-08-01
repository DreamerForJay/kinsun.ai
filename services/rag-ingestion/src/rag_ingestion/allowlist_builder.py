"""Rebuild the Allowlist entry set from the approved chunk files.

Recomputing 262 hashes by hand is the step most likely to go wrong, and a
single wrong byte rejects the whole run. This does the mechanical part only:
hashes, per-source counts, and entry records.

It deliberately does not touch governance. Manifest status, owner risk
acceptance, human review, and production status are copied verbatim, and a
chunk that is new to the manifest inherits the conservative per-entry markers
rather than the state of its neighbours. Deciding that a source has been
reviewed is a human act, not a side effect of running a script.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rag_ingestion.allowlist import CHUNK_ID_PATTERN

# Copied onto entries the manifest has not seen before. Every one is the
# blocking value: a new chunk is unreviewed until a human says otherwise.
NEW_ENTRY_MARKERS: dict[str, Any] = {
    "signature_required": True,
    "review_status": "needs_review",
    "human_source_review": "NOT_COMPLETED",
    "embedding_status": "NOT_STARTED",
    "opensearch_indexing_status": "NOT_STARTED",
    "production_gate": "BLOCKED",
}
_CARRIED_ENTRY_KEYS = (
    "allowed_use",
    *NEW_ENTRY_MARKERS,
)


class AllowlistBuildError(ValueError):
    """Raised when the approved chunks cannot produce a consistent manifest."""


@dataclass(frozen=True, slots=True)
class ChunkRecord:
    chunk_id: str
    chunk_index: int
    source_id: str
    text_sha256: str
    embedding_text_sha256: str
    source_title: str | None
    source_version: str | None
    file_name: str


@dataclass(slots=True)
class AllowlistRebuild:
    """The proposed manifest plus everything an operator must review."""

    serialized: bytes
    sha256: str
    previous_sha256: str
    chunk_count: int
    source_count: int
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    rehashed: list[str] = field(default_factory=list)
    governance: dict[str, str] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        """Whether any chunk actually differs, ignoring JSON formatting.

        Rewriting the manifest changes its SHA-256 even when the content is
        identical, and that alone would force a pointless index rebuild. Only
        a real difference is worth spending one on.
        """

        return bool(self.added or self.removed or self.rehashed)

    @property
    def serialized_differs(self) -> bool:
        return self.sha256 != self.previous_sha256

    def to_summary(self) -> dict[str, Any]:
        return {
            "status": "REBUILT" if self.changed else "UNCHANGED",
            "formatting_only_difference": self.serialized_differs and not self.changed,
            "chunk_count": self.chunk_count,
            "source_count": self.source_count,
            "added_chunk_count": len(self.added),
            "removed_chunk_count": len(self.removed),
            "rehashed_chunk_count": len(self.rehashed),
            "added_chunk_ids": self.added[:10],
            "removed_chunk_ids": self.removed[:10],
            "rehashed_chunk_ids": self.rehashed[:10],
            "previous_allowlist_sha256": self.previous_sha256,
            "allowlist_sha256": self.sha256,
            "governance": self.governance,
        }


def sha256_text(value: str) -> str:
    """Hash exactly as the validator does, so the two can never disagree."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_approved_chunks(chunks_dir: Path) -> list[ChunkRecord]:
    directory = chunks_dir.expanduser().resolve()
    if "pending-revalidation" in {part.casefold() for part in directory.parts}:
        raise AllowlistBuildError("pending-revalidation is never an allowed chunks directory")
    if not directory.is_dir():
        raise AllowlistBuildError("chunks directory does not exist")
    files = sorted(directory.glob("*.jsonl"), key=lambda item: item.name)
    if not files:
        raise AllowlistBuildError("approved chunks directory contains no JSONL files")

    records: dict[str, ChunkRecord] = {}
    for file_path in files:
        with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for line_number, line in enumerate(handle, start=1):
                location = f"{file_path.name}:{line_number}"
                if not line.strip():
                    raise AllowlistBuildError(f"blank JSONL line at {location}")
                try:
                    data = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise AllowlistBuildError(f"invalid JSONL at {location}") from exc
                if not isinstance(data, dict):
                    raise AllowlistBuildError(f"JSONL record must be an object at {location}")
                record = _to_record(data, location, file_path.name)
                if record.chunk_id in records:
                    raise AllowlistBuildError(f"duplicate chunk_id {record.chunk_id} at {location}")
                records[record.chunk_id] = record
    return list(records.values())


def _to_record(data: dict[str, Any], location: str, file_name: str) -> ChunkRecord:
    chunk_id = data.get("chunk_id")
    if not isinstance(chunk_id, str) or not CHUNK_ID_PATTERN.fullmatch(chunk_id):
        raise AllowlistBuildError(f"invalid chunk_id at {location}")
    chunk_index = data.get("chunk_index")
    if isinstance(chunk_index, bool) or not isinstance(chunk_index, int) or chunk_index < 0:
        raise AllowlistBuildError(f"chunk_index must be a non-negative integer at {location}")
    source_id = data.get("source_id")
    if not isinstance(source_id, str) or not source_id.strip():
        raise AllowlistBuildError(f"source_id missing or blank at {location}")
    text = data.get("text")
    embedding_text = data.get("embedding_text")
    if not isinstance(text, str) or not text.strip():
        raise AllowlistBuildError(f"text missing or blank at {location}")
    if not isinstance(embedding_text, str) or not embedding_text.strip():
        raise AllowlistBuildError(f"embedding_text missing or blank at {location}")
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    return ChunkRecord(
        chunk_id=chunk_id,
        chunk_index=chunk_index,
        source_id=source_id,
        text_sha256=sha256_text(text),
        embedding_text_sha256=sha256_text(embedding_text),
        source_title=_first_string(data, metadata, "source_title", "document_title"),
        source_version=_first_string(data, metadata, "source_version", "document_version"),
        file_name=file_name,
    )


def _first_string(data: dict[str, Any], metadata: dict[str, Any], *names: str) -> str | None:
    for name in names:
        for container in (data, metadata):
            value = container.get(name)
            if isinstance(value, str) and value.strip():
                return value
    return None


def rebuild_allowlist(*, manifest_path: Path, chunks_dir: Path) -> AllowlistRebuild:
    """Return the manifest the approved chunks imply, without writing it."""

    try:
        previous_bytes = manifest_path.read_bytes()
        document = json.loads(previous_bytes.decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AllowlistBuildError(f"cannot read allowlist: {type(exc).__name__}") from exc
    if not isinstance(document, dict):
        raise AllowlistBuildError("allowlist root must be an object")

    sources = document.get("sources")
    if not isinstance(sources, list) or not sources:
        raise AllowlistBuildError("allowlist sources must be a non-empty array")
    number_by_source_id: dict[str, int] = {}
    for source in sources:
        if not isinstance(source, dict):
            raise AllowlistBuildError("allowlist source must be an object")
        source_id = source.get("source_id")
        source_number = source.get("source_number")
        if not isinstance(source_id, str) or isinstance(source_number, bool):
            raise AllowlistBuildError("allowlist source is missing source_id/source_number")
        if not isinstance(source_number, int):
            raise AllowlistBuildError("allowlist source_number must be an integer")
        number_by_source_id[source_id] = source_number

    records = read_approved_chunks(chunks_dir)
    unknown = sorted({record.source_id for record in records} - set(number_by_source_id))
    if unknown:
        # source_number ties a source back to the human review catalogue. A
        # script must not invent one.
        raise AllowlistBuildError(
            "add a sources[] entry with the reviewed source_number first: " + ", ".join(unknown)
        )

    previous_entries = document.get("entries")
    previous_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(previous_entries, list):
        for entry in previous_entries:
            if isinstance(entry, dict) and isinstance(entry.get("chunk_id"), str):
                previous_by_id[entry["chunk_id"]] = entry

    records.sort(key=lambda record: (number_by_source_id[record.source_id], record.chunk_index))
    entries: list[dict[str, Any]] = []
    added: list[str] = []
    rehashed: list[str] = []
    for record in records:
        previous = previous_by_id.get(record.chunk_id)
        if previous is None:
            added.append(record.chunk_id)
        elif (
            previous.get("text_sha256") != record.text_sha256
            or previous.get("embedding_text_sha256") != record.embedding_text_sha256
        ):
            rehashed.append(record.chunk_id)
        entries.append(_entry_for(record, previous, number_by_source_id[record.source_id]))

    removed = sorted(set(previous_by_id) - {record.chunk_id for record in records})

    per_source: dict[int, int] = {}
    for record in records:
        number = number_by_source_id[record.source_id]
        per_source[number] = per_source.get(number, 0) + 1
    used_sources = [source for source in sources if per_source.get(source["source_number"], 0) > 0]
    for source in used_sources:
        source["chunk_count"] = per_source[source["source_number"]]

    document["sources"] = used_sources
    document["entries"] = entries
    document["source_count"] = len(used_sources)
    document["chunk_count"] = len(entries)

    serialized = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return AllowlistRebuild(
        serialized=serialized,
        sha256=hashlib.sha256(serialized).hexdigest(),
        previous_sha256=hashlib.sha256(previous_bytes).hexdigest(),
        chunk_count=len(entries),
        source_count=len(used_sources),
        added=added,
        removed=removed,
        rehashed=rehashed,
        governance={
            key: str(document.get(key, "MISSING"))
            for key in (
                "status",
                "allowed_use",
                "project_owner_risk_acceptance",
                "human_source_review",
                "production_status",
            )
        },
    )


def _entry_for(
    record: ChunkRecord, previous: dict[str, Any] | None, source_number: int
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "source_number": source_number,
        "source_id": record.source_id,
        "chunk_id": record.chunk_id,
        "chunk_index": record.chunk_index,
        "text_sha256": record.text_sha256,
        "embedding_text_sha256": record.embedding_text_sha256,
    }
    if record.source_title is not None:
        entry["source_title"] = record.source_title
    elif previous is not None and isinstance(previous.get("source_title"), str):
        entry["source_title"] = previous["source_title"]
    if record.source_version is not None:
        entry["source_version"] = record.source_version
    elif previous is not None and isinstance(previous.get("source_version"), str):
        entry["source_version"] = previous["source_version"]

    for key in _CARRIED_ENTRY_KEYS:
        if previous is not None and key in previous:
            entry[key] = previous[key]
        elif key in NEW_ENTRY_MARKERS:
            entry[key] = NEW_ENTRY_MARKERS[key]
    return entry


def write_allowlist(rebuild: AllowlistRebuild, manifest_path: Path) -> None:
    """Replace the manifest atomically so a failed write cannot truncate it."""

    temporary = manifest_path.with_name(f".{manifest_path.name}.rebuild.tmp")
    try:
        temporary.write_bytes(rebuild.serialized)
        temporary.replace(manifest_path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
