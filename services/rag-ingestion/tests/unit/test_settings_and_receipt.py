from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import write_dataset

from rag_ingestion.allowlist import AllowlistGovernanceError, load_allowlist
from rag_ingestion.receipt import new_receipt, write_receipt
from rag_ingestion.settings import IngestionSettings, SettingsError


def isolated_settings(**values: object) -> IngestionSettings:
    """Build settings without reading a developer's repository-local .env."""

    return IngestionSettings(_env_file=None, **values)


def test_settings_reject_non_1024_dimension() -> None:
    with pytest.raises(ValueError, match="1024"):
        isolated_settings(BEDROCK_EMBEDDING_DIMENSION=1536)


def test_settings_reject_production_index_name() -> None:
    with pytest.raises(ValueError, match="staging"):
        isolated_settings(OPENSEARCH_INDEX="knowledge-production-v1")


def test_settings_do_not_require_aws_for_local_validation() -> None:
    settings = isolated_settings(
        RAG_ALLOWLIST_PATH="allowlist.json",
        RAG_CHUNKS_DIR="approved",
    )

    assert settings.require_paths() == (Path("allowlist.json"), Path("approved"))
    assert settings.rag_require_owner_signature is False
    assert settings.rag_production_enabled is False
    with pytest.raises(SettingsError, match="Bedrock"):
        settings.require_bedrock()


@pytest.mark.parametrize("forbidden", ["pending-revalidation", "not-authorized"])
def test_uncleared_chunk_directories_are_refused_before_any_load(forbidden: str) -> None:
    settings = isolated_settings(
        RAG_ALLOWLIST_PATH="allowlist.json",
        RAG_CHUNKS_DIR=f"data/rag-chunks/{forbidden}",
    )

    with pytest.raises(SettingsError, match=forbidden):
        settings.require_paths()


def test_smoke_test_requires_explicit_agent_runtime_base_url() -> None:
    with pytest.raises(SettingsError, match="AGENT_RUNTIME_BASE_URL"):
        isolated_settings(AGENT_RUNTIME_BASE_URL="").require_agent_runtime_base_url()

    assert (
        isolated_settings(
            AGENT_RUNTIME_BASE_URL="http://agent-runtime.test:8000/"
        ).require_agent_runtime_base_url()
        == "http://agent-runtime.test:8000"
    )


def test_unrelated_dotenv_keys_are_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text(
        "UNRELATED_DATABASE_URL=postgresql://example.invalid/db\nRAG_MODE=staging\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    settings = IngestionSettings(_env_file=tmp_path / ".env")

    assert settings.rag_mode == "staging"


def test_governance_environment_flags_default_false_and_parse_explicit_values() -> None:
    defaults = isolated_settings()
    explicit = isolated_settings(
        RAG_REQUIRE_OWNER_SIGNATURE="true",
        RAG_PRODUCTION_ENABLED="false",
    )

    assert defaults.rag_require_owner_signature is False
    assert defaults.rag_production_enabled is False
    assert explicit.rag_require_owner_signature is True
    assert explicit.rag_production_enabled is False


@pytest.mark.parametrize(
    "settings",
    [
        isolated_settings(RAG_MODE="production", RAG_PRODUCTION_ENABLED=False),
        isolated_settings(RAG_MODE="staging", RAG_PRODUCTION_ENABLED=True),
    ],
)
def test_first_release_refuses_non_staging_external_targets(settings: IngestionSettings) -> None:
    with pytest.raises(SettingsError, match="only execute staging"):
        settings.assert_staging_only_external_execution()


def test_receipt_contains_governance_and_never_vectors_or_text(tmp_path: Path) -> None:
    manifest_path, chunks_dir = write_dataset(tmp_path / "dataset", effective=False)
    allowlist = load_allowlist(manifest_path)
    receipt = new_receipt(
        allowlist=allowlist,
        chunks_dir=chunks_dir,
        model_id="configured-model-id",
        dimension=1024,
        index_name="synthetic-staging-v1",
        index_alias="synthetic-staging",
        mode="staging",
        expected_allowlist_sha256=allowlist.sha256,
        require_owner_signature=False,
        production_enabled=False,
    )
    receipt.validated_chunk_count = 1
    receipt.complete("BLOCKED")
    output = tmp_path / "receipt.json"

    write_receipt(receipt, output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["governance"]["project_owner_risk_acceptance"] == "NOT_SIGNED"
    assert payload["governance"]["human_source_review"] == "NOT_COMPLETED"
    assert payload["governance"]["governance_status"] == "UNSIGNED_DEVELOPMENT_OVERRIDE"
    assert payload["governance"]["production_approved"] is False
    serialized = json.dumps(payload)
    assert '"embedding"' not in serialized
    assert '"vector"' not in serialized
    assert '"text"' not in serialized


def test_receipt_revalidates_allowlist_attestation_instead_of_trusting_caller(
    tmp_path: Path,
) -> None:
    manifest_path, chunks_dir = write_dataset(tmp_path / "dataset", effective=False)
    allowlist = load_allowlist(manifest_path)

    with pytest.raises(AllowlistGovernanceError, match="does not match"):
        new_receipt(
            allowlist=allowlist,
            chunks_dir=chunks_dir,
            model_id="configured-model-id",
            dimension=1024,
            index_name="synthetic-staging-v1",
            index_alias="synthetic-staging",
            mode="staging",
            expected_allowlist_sha256="0" * 64,
            require_owner_signature=False,
            production_enabled=False,
        )
