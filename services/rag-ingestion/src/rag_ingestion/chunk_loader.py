"""Strict JSONL loading limited to the explicit allowlist."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rag_ingestion.allowlist import CHUNK_ID_PATTERN, Allowlist


class ChunkLoadError(ValueError):
    """Raised before validation when the approved JSONL set is not exact."""


@dataclass(frozen=True, slots=True)
class LoadedChunk:
    data: dict[str, Any]
    file_path: Path
    line_number: int

    @property
    def chunk_id(self) -> str:
        value = self.data.get("chunk_id")
        return value if isinstance(value, str) else ""


def load_allowlisted_chunks(chunks_dir: Path, allowlist: Allowlist) -> tuple[LoadedChunk, ...]:
    """Load the exact approved set; unknown, missing, or duplicate IDs are fatal."""

    directory = chunks_dir.expanduser().resolve()
    if "pending-revalidation" in {part.casefold() for part in directory.parts}:
        raise ChunkLoadError("pending-revalidation is never an allowed chunks directory")
    if not directory.is_dir():
        raise ChunkLoadError("chunks directory does not exist")

    files = sorted(directory.glob("*.jsonl"), key=lambda item: item.name)
    if not files:
        raise ChunkLoadError("approved chunks directory contains no JSONL files")

    allowed_ids = set(allowlist.allowed_chunk_ids)
    loaded_by_id: dict[str, LoadedChunk] = {}
    for file_path in files:
        resolved_file = file_path.resolve()
        if directory not in resolved_file.parents:
            raise ChunkLoadError("JSONL file resolves outside the approved chunks directory")
        try:
            handle = resolved_file.open("r", encoding="utf-8-sig", newline="")
        except OSError as exc:
            raise ChunkLoadError(f"cannot read {file_path.name}: {type(exc).__name__}") from exc
        with handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    raise ChunkLoadError(f"blank JSONL line at {file_path.name}:{line_number}")
                try:
                    data = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ChunkLoadError(
                        f"invalid JSONL at {file_path.name}:{line_number}"
                    ) from exc
                if not isinstance(data, dict):
                    raise ChunkLoadError(
                        f"JSONL record must be an object at {file_path.name}:{line_number}"
                    )
                chunk_id = data.get("chunk_id")
                if not isinstance(chunk_id, str) or not CHUNK_ID_PATTERN.fullmatch(chunk_id):
                    raise ChunkLoadError(f"invalid chunk_id at {file_path.name}:{line_number}")
                if chunk_id not in allowed_ids:
                    raise ChunkLoadError(f"chunk_id is outside allowlist: {chunk_id}")
                if chunk_id in loaded_by_id:
                    previous = loaded_by_id[chunk_id]
                    raise ChunkLoadError(
                        "duplicate chunk_id "
                        f"{chunk_id} at {previous.file_path.name}:{previous.line_number} "
                        f"and {file_path.name}:{line_number}"
                    )
                loaded_by_id[chunk_id] = LoadedChunk(
                    data=data,
                    file_path=resolved_file,
                    line_number=line_number,
                )

    missing = [chunk_id for chunk_id in allowlist.allowed_chunk_ids if chunk_id not in loaded_by_id]
    if missing:
        preview = ", ".join(missing[:3])
        suffix = "..." if len(missing) > 3 else ""
        raise ChunkLoadError(f"allowlisted chunks are missing: {preview}{suffix}")
    return tuple(loaded_by_id[chunk_id] for chunk_id in allowlist.allowed_chunk_ids)
