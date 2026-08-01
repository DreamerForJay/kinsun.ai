"""Generate staging document embeddings into a non-repository temp artifact."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "rag-ingestion" / "src"))

from rag_ingestion.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main(["generate-embeddings", "--repository-root", str(REPO_ROOT)]))
