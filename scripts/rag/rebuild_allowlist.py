"""Recompute Allowlist hashes and counts from the approved chunk files.

Reports by default. Pass --write to replace the manifest. Governance fields
are never changed, and the new SHA-256 must still be placed into
RAG_ALLOWLIST_EXPECTED_SHA256 by hand: the manifest cannot attest itself.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "rag-ingestion" / "src"))

from rag_ingestion.allowlist_builder import (  # noqa: E402
    AllowlistBuildError,
    rebuild_allowlist,
    write_allowlist,
)
from rag_ingestion.settings import SettingsError, load_settings  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="rebuild the staging RAG allowlist")
    parser.add_argument("--write", action="store_true", help="replace the manifest on disk")
    parser.add_argument("--config-dir")
    args = parser.parse_args(argv)

    config_dir = Path(args.config_dir) if args.config_dir else REPO_ROOT / "config" / "rag"
    try:
        settings = load_settings(
            embedding_config_path=config_dir / "embedding.yaml",
            index_config_path=config_dir / "opensearch-index-v1.json",
            staging_config_path=config_dir / "staging-filters.yaml",
            repository_root=REPO_ROOT,
        )
        manifest_path, chunks_dir = settings.require_paths()
        rebuild = rebuild_allowlist(manifest_path=manifest_path, chunks_dir=chunks_dir)
    except (AllowlistBuildError, SettingsError) as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "command": "rebuild-allowlist",
                    "error_type": type(exc).__name__,
                    "failure_reason": str(exc),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1

    summary = rebuild.to_summary()
    summary["written"] = False
    if args.write and rebuild.changed:
        write_allowlist(rebuild, manifest_path)
        summary["written"] = True
    if rebuild.changed:
        summary["next_step"] = (
            "set RAG_ALLOWLIST_EXPECTED_SHA256 to allowlist_sha256, then rebuild the index"
        )
    elif rebuild.serialized_differs:
        summary["next_step"] = (
            "no chunk changed; rewriting would only reformat and would invalidate "
            "the current RAG_ALLOWLIST_EXPECTED_SHA256 for nothing"
        )
    else:
        summary["next_step"] = "nothing to do"
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
