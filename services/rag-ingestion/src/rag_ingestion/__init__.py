"""Offline, fail-closed RAG ingestion primitives."""

from rag_ingestion.allowlist import Allowlist, AllowlistGovernanceError, load_allowlist
from rag_ingestion.chunk_loader import ChunkLoadError, LoadedChunk, load_allowlisted_chunks
from rag_ingestion.validator import (
    ChunkValidationError,
    ValidatedChunk,
    ValidationResult,
    validate_chunks,
)

__all__ = [
    "Allowlist",
    "AllowlistGovernanceError",
    "ChunkLoadError",
    "ChunkValidationError",
    "LoadedChunk",
    "ValidatedChunk",
    "ValidationResult",
    "load_allowlist",
    "load_allowlisted_chunks",
    "validate_chunks",
]
