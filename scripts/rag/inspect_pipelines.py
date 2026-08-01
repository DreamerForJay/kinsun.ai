"""Inspect configured search pipelines without changing OpenSearch resources."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_SRC = REPO_ROOT / "services" / "rag-ingestion" / "src"
if str(SERVICE_SRC) not in sys.path:
    sys.path.insert(0, str(SERVICE_SRC))

from rag_ingestion.cli import main


if __name__ == "__main__":
    raise SystemExit(main(["inspect-pipelines", "--repository-root", str(REPO_ROOT)]))
