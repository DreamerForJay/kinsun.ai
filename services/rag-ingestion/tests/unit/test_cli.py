from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from conftest import write_dataset
from opensearchpy.exceptions import RequestError

from rag_ingestion import cli
from rag_ingestion.allowlist import (
    UNSIGNED_DEVELOPMENT_OVERRIDE,
    AllowlistGovernanceError,
    load_allowlist,
)
from rag_ingestion.bedrock_embedder import EmbeddingBatchError, EmbeddingResult
from rag_ingestion.bulk_ingester import BulkIngestionError, BulkIngestionReport
from rag_ingestion.chunk_loader import load_allowlisted_chunks
from rag_ingestion.index_manager import IndexConfigurationError, SearchPipelineDefinition
from rag_ingestion.opensearch_client import BulkOperationError
from rag_ingestion.receipt import new_receipt
from rag_ingestion.settings import SettingsError
from rag_ingestion.smoke_test import AgentRuntimeSmokeReport, SmokeTestError
from rag_ingestion.validator import validate_chunks


class FakeSettings:
    embedding_batch_size = 96
    embedding_truncate = "NONE"
    rag_mode = "staging"
    rag_require_owner_signature = False
    rag_production_enabled = False

    def __init__(self, artifact_path: Path, expected_sha256: str | None) -> None:
        self.artifact_path = artifact_path
        self.rag_allowlist_expected_sha256 = expected_sha256

    def require_bedrock(self) -> tuple[str, str, int]:
        return "configured-region", "configured-model-id", 1024

    def embedding_artifact_path(self, repository_root: Path) -> Path:
        return self.artifact_path

    def assert_staging_only_external_execution(self) -> None:
        if self.rag_mode != "staging" or self.rag_production_enabled:
            raise SettingsError("staging only")


class FakeContext:
    def __init__(self, repository_root: Path, settings: FakeSettings, result: Any) -> None:
        self.repository_root = repository_root
        self.settings = settings
        self.result = result
        self.smoke_config_path = repository_root / "config" / "rag" / "smoke-test.yaml"

    def validate(self) -> Any:
        return self.result


class FakeIngestSettings(FakeSettings):
    bedrock_embedding_model_id = "configured-model-id"
    bedrock_embedding_dimension = 1024
    agent_runtime_base_url = "http://agent-runtime.test:8000"

    def __init__(
        self,
        artifact_path: Path,
        expected_sha256: str,
        manifest_path: Path,
        chunks_dir: Path,
    ) -> None:
        super().__init__(artifact_path, expected_sha256)
        self.manifest_path = manifest_path
        self.chunks_dir = chunks_dir

    def require_opensearch(self) -> tuple[str, str, str, str]:
        return (
            "configured-region",
            "https://synthetic.us-east-1.aoss.amazonaws.com",
            "synthetic-staging-v1",
            "synthetic-staging",
        )

    def require_paths(self) -> tuple[Path, Path]:
        return self.manifest_path, self.chunks_dir

    def require_agent_runtime_base_url(self) -> str:
        return self.agent_runtime_base_url


class FakeGateway:
    def __init__(
        self,
        events: list[str],
        *,
        fail_alias: bool = False,
        alias_target_names: tuple[str, ...] = (),
    ) -> None:
        self.events = events
        self.fail_alias = fail_alias
        self.alias_target_names = alias_target_names

    def alias_targets(self, alias_name: str) -> tuple[str, ...]:
        return self.alias_target_names

    def set_alias(self, index_name: str, alias_name: str) -> None:
        is_new_index = index_name == "synthetic-staging-v1"
        self.events.append("alias" if is_new_index else "restore-alias")
        if self.fail_alias and is_new_index:
            raise RuntimeError("synthetic alias failure")

    def delete_index(self, index_name: str) -> None:
        self.events.append("delete-index")

    def smoke_test_current_normal_rag(self, index_name: str) -> int:
        self.events.append(f"smoke:{index_name}")
        return 1


class InspectGateway:
    def __init__(self, pipelines: dict[str, dict[str, Any]]) -> None:
        self.pipelines = pipelines
        self.pipeline_gets: list[str] = []

    def get_search_pipeline(self, pipeline_name: str) -> dict[str, Any] | None:
        self.pipeline_gets.append(pipeline_name)
        return self.pipelines.get(pipeline_name)


class FakeBulkIngester:
    events: list[str] = []

    def __init__(self, client: Any, *, dimension: int) -> None:
        assert dimension == 1024

    def ingest(self, **kwargs: Any) -> BulkIngestionReport:
        assert kwargs["activate_alias"] is False
        self.events.append("bulk-verified")
        return BulkIngestionReport(
            indexed_document_count=1,
            duplicate_id_count=0,
            vector_dimension=1024,
            alias_activated=False,
        )


def test_cli_embedding_failure_reports_success_and_failure_counts(
    monkeypatch: Any, capsys: Any
) -> None:
    monkeypatch.setattr(cli, "_load_context", lambda args: object())

    def fail_embedding(context: Any) -> dict[str, Any]:
        raise EmbeddingBatchError(
            "synthetic failure",
            success_count=96,
            failure_count=166,
        )

    monkeypatch.setattr(cli, "_generate_embeddings", fail_embedding)

    assert cli.main(["generate-embeddings"]) == 1
    failure = json.loads(capsys.readouterr().err)
    assert failure["embedding_success_count"] == 96
    assert failure["embedding_failure_count"] == 166


def test_inspect_pipelines_is_read_only_and_reports_governance_and_mismatch(
    tmp_path: Path, monkeypatch: Any
) -> None:
    manifest_path, chunks_dir = write_dataset(tmp_path / "dataset", effective=False)
    allowlist = load_allowlist(manifest_path)
    validation = validate_chunks(load_allowlisted_chunks(chunks_dir, allowlist), allowlist)
    context = FakeContext(
        tmp_path / "repo",
        FakeIngestSettings(
            tmp_path / "external" / "embeddings.jsonl", allowlist.sha256, manifest_path, chunks_dir
        ),
        (allowlist, validation),
    )
    natural = SearchPipelineDefinition(
        profile="natural_language",
        name="synthetic-natural-staging-v1",
        bm25_weight=0.4,
        vector_weight=0.6,
        body={"phase_results_processors": [{"normalization-processor": {"x": 1}}]},
    )
    legal = SearchPipelineDefinition(
        profile="legal",
        name="synthetic-legal-staging-v1",
        bm25_weight=0.65,
        vector_weight=0.35,
        body={"phase_results_processors": [{"normalization-processor": {"x": 2}}]},
    )
    gateway = InspectGateway(
        {
            natural.name: natural.body,
            legal.name: {"phase_results_processors": [{"normalization-processor": {"x": 3}}]},
        }
    )
    context.gateway = lambda: gateway
    monkeypatch.setattr(cli, "_load_pipeline_definitions", lambda context: (natural, legal))

    summary = cli._inspect_pipelines(context)

    assert summary == {
        "status": "INSPECTED",
        "governance_status": UNSIGNED_DEVELOPMENT_OVERRIDE,
        "production_approved": False,
        "search_pipelines": [
            {"name": natural.name, "status": "VISIBLE", "config_match": True},
            {"name": legal.name, "status": "VISIBLE", "config_match": False},
        ],
    }
    assert gateway.pipeline_gets == [natural.name, legal.name]


def test_cli_reports_safe_dependency_diagnostics(monkeypatch: Any, capsys: Any) -> None:
    monkeypatch.setattr(cli, "_load_context", lambda args: object())

    class SyntheticRequestError(RuntimeError):
        status_code = 400
        error = "mapper_parsing_exception"

    def fail_create_index(context: Any) -> dict[str, Any]:
        raise SyntheticRequestError("sensitive upstream detail is intentionally omitted")

    monkeypatch.setattr(cli, "_create_index", fail_create_index)

    assert cli.main(["create-index"]) == 1
    failure = json.loads(capsys.readouterr().err)
    assert failure["dependency_status_code"] == 400
    assert failure["dependency_error"] == "mapper_parsing_exception"
    assert "message" not in failure


@pytest.mark.parametrize(
    "error_type",
    [IndexConfigurationError, SettingsError, SmokeTestError],
)
def test_cli_reports_safe_local_configuration_failure_reason(
    error_type: type[ValueError], monkeypatch: Any, capsys: Any
) -> None:
    monkeypatch.setattr(cli, "_load_context", lambda args: object())
    reason = "configured staging index does not match the validated mapping"

    def fail_create_index(context: Any) -> dict[str, Any]:
        raise error_type(reason)

    monkeypatch.setattr(cli, "_create_index", fail_create_index)

    assert cli.main(["create-index"]) == 1

    failure = json.loads(capsys.readouterr().err)
    assert failure["failure_reason"] == reason


@pytest.mark.parametrize("reason", ["unsafe\nreason", "x" * 513])
def test_cli_rejects_unsafe_local_configuration_failure_reason(
    reason: str, monkeypatch: Any, capsys: Any
) -> None:
    monkeypatch.setattr(cli, "_load_context", lambda args: object())

    def fail_create_index(context: Any) -> dict[str, Any]:
        raise IndexConfigurationError(reason)

    monkeypatch.setattr(cli, "_create_index", fail_create_index)

    assert cli.main(["create-index"]) == 1

    failure = json.loads(capsys.readouterr().err)
    assert "failure_reason" not in failure


def test_cli_create_index_reports_bounded_opensearch_reason(monkeypatch: Any, capsys: Any) -> None:
    monkeypatch.setattr(cli, "_load_context", lambda args: object())
    reason = "unknown parameter [engine] in vector index mapping"

    def fail_create_index(context: Any) -> dict[str, Any]:
        raise RequestError(
            400,
            "illegal_argument_exception",
            {"error": {"reason": reason}},
        )

    monkeypatch.setattr(cli, "_create_index", fail_create_index)

    assert cli.main(["create-index"]) == 1

    failure = json.loads(capsys.readouterr().err)
    assert failure["dependency_reason"] == reason
    assert "failure_reason" not in failure


def test_cli_create_index_uses_safe_root_cause_reason(monkeypatch: Any, capsys: Any) -> None:
    monkeypatch.setattr(cli, "_load_context", lambda args: object())
    root_cause_reason = "mapping definition is incompatible with this collection"

    def fail_create_index(context: Any) -> dict[str, Any]:
        raise RequestError(
            400,
            "illegal_argument_exception",
            {"error": {"root_cause": [{"reason": root_cause_reason}]}},
        )

    monkeypatch.setattr(cli, "_create_index", fail_create_index)

    assert cli.main(["create-index"]) == 1

    failure = json.loads(capsys.readouterr().err)
    assert failure["dependency_reason"] == root_cause_reason


@pytest.mark.parametrize("reason", ["unsafe\nreason", "x" * 513])
def test_cli_only_emits_safe_create_index_request_reason(
    reason: str, monkeypatch: Any, capsys: Any
) -> None:
    monkeypatch.setattr(cli, "_load_context", lambda args: object())

    def fail_create_index(context: Any) -> dict[str, Any]:
        raise RequestError(
            400,
            "illegal_argument_exception",
            {"error": {"reason": reason}},
        )

    monkeypatch.setattr(cli, "_create_index", fail_create_index)

    assert cli.main(["create-index"]) == 1

    failure = json.loads(capsys.readouterr().err)
    assert "dependency_reason" not in failure


def test_cli_does_not_emit_request_reason_for_ingest(monkeypatch: Any, capsys: Any) -> None:
    monkeypatch.setattr(cli, "_load_context", lambda args: object())

    def fail_ingest(context: Any) -> dict[str, Any]:
        raise RequestError(
            400,
            "illegal_argument_exception",
            {"error": {"reason": "document source content must stay out of logs"}},
        )

    monkeypatch.setattr(cli, "_ingest", fail_ingest)

    assert cli.main(["ingest"]) == 1

    failure = json.loads(capsys.readouterr().err)
    assert "dependency_reason" not in failure


def test_generate_embeddings_passes_effective_allowlist_to_guarded_workflow(
    tmp_path: Path, monkeypatch: Any
) -> None:
    manifest_path, chunks_dir = write_dataset(tmp_path / "dataset", effective=False)
    allowlist = load_allowlist(manifest_path)
    validation = validate_chunks(load_allowlisted_chunks(chunks_dir, allowlist), allowlist)
    context = FakeContext(
        tmp_path / "repo",
        FakeSettings(tmp_path / "external" / "embeddings.jsonl", allowlist.sha256),
        (allowlist, validation),
    )
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        cli.BedrockEmbedder,
        "from_boto3",
        lambda **kwargs: object(),
    )

    def fake_generate_embedding_artifact(**kwargs: Any) -> EmbeddingResult:
        captured.update(kwargs)
        return EmbeddingResult(vectors=((0.0,) * 1024,), success_count=1, failure_count=0)

    monkeypatch.setattr(cli, "generate_embedding_artifact", fake_generate_embedding_artifact)

    summary = cli._generate_embeddings(context)

    assert captured["allowlist"] is allowlist
    assert captured["expected_allowlist_sha256"] == allowlist.sha256
    assert captured["rag_mode"] == "staging"
    assert captured["require_owner_signature"] is False
    assert captured["production_enabled"] is False
    assert summary["status"] == "EMBEDDED"
    assert summary["governance_status"] == UNSIGNED_DEVELOPMENT_OVERRIDE
    assert summary["production_approved"] is False


@pytest.mark.parametrize(
    "handler",
    [
        cli._create_index,
        cli._generate_embeddings,
        cli._ingest,
        cli._verify_index,
        cli._smoke_test,
    ],
)
def test_external_commands_check_attestation_before_sdk_initialization(
    handler: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    manifest_path, chunks_dir = write_dataset(tmp_path / "dataset", effective=True)
    allowlist = load_allowlist(manifest_path)
    validation = validate_chunks(load_allowlisted_chunks(chunks_dir, allowlist), allowlist)
    context = FakeContext(
        tmp_path / "repo",
        FakeSettings(tmp_path / "external" / "embeddings.jsonl", None),
        (allowlist, validation),
    )
    sdk_calls: list[str] = []
    monkeypatch.setattr(
        cli.BedrockEmbedder,
        "from_boto3",
        lambda **kwargs: sdk_calls.append("bedrock"),
    )
    monkeypatch.setattr(
        cli.OpenSearchGateway,
        "from_aws",
        lambda **kwargs: sdk_calls.append("opensearch"),
    )

    with pytest.raises(AllowlistGovernanceError, match="attestation"):
        handler(context)

    assert sdk_calls == []


def test_cli_governance_failure_log_marks_unsigned_development_override(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    manifest_path, chunks_dir = write_dataset(tmp_path / "dataset", effective=False)
    allowlist = load_allowlist(manifest_path)
    validation = validate_chunks(load_allowlisted_chunks(chunks_dir, allowlist), allowlist)
    context = FakeContext(
        tmp_path / "repo",
        FakeSettings(tmp_path / "external" / "embeddings.jsonl", None),
        (allowlist, validation),
    )
    monkeypatch.setattr(cli, "_load_context", lambda args: context)

    assert cli.main(["create-index"]) == 1

    failure = json.loads(capsys.readouterr().err)
    assert failure["error_type"] == "AllowlistGovernanceError"
    assert failure["governance_status"] == UNSIGNED_DEVELOPMENT_OVERRIDE
    assert failure["production_approved"] is False


def test_cli_post_gate_failure_log_retains_unsigned_governance_markers(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    manifest_path, chunks_dir = write_dataset(tmp_path / "dataset", effective=False)
    allowlist = load_allowlist(manifest_path)
    validation = validate_chunks(load_allowlisted_chunks(chunks_dir, allowlist), allowlist)
    context = FakeContext(
        tmp_path / "repo",
        FakeSettings(tmp_path / "external" / "embeddings.jsonl", allowlist.sha256),
        (allowlist, validation),
    )
    monkeypatch.setattr(cli, "_load_context", lambda args: context)

    def fail_after_governance_gate(active_context: FakeContext) -> dict[str, Any]:
        active_allowlist, _ = active_context.validate()
        cli._assert_allowlist_execution(active_context, active_allowlist)
        raise RuntimeError("synthetic provider failure")

    monkeypatch.setattr(cli, "_create_index", fail_after_governance_gate)

    assert cli.main(["create-index"]) == 1

    failure = json.loads(capsys.readouterr().err)
    assert failure["error_type"] == "RuntimeError"
    assert failure["governance_status"] == UNSIGNED_DEVELOPMENT_OVERRIDE
    assert failure["production_approved"] is False


def _ingest_context(tmp_path: Path) -> tuple[FakeContext, str]:
    manifest_path, chunks_dir = write_dataset(tmp_path / "dataset", effective=True)
    allowlist = load_allowlist(manifest_path)
    validation = validate_chunks(load_allowlisted_chunks(chunks_dir, allowlist), allowlist)
    settings = FakeIngestSettings(
        tmp_path / "external" / "embeddings.jsonl",
        allowlist.sha256,
        manifest_path,
        chunks_dir,
    )
    return FakeContext(tmp_path / "repo", settings, (allowlist, validation)), allowlist.sha256


def _patch_ingest_dependencies(
    monkeypatch: Any,
    *,
    events: list[str],
    gateway: FakeGateway,
    tmp_path: Path,
    fail_completed_receipt: bool = False,
) -> None:
    FakeBulkIngester.events = events
    monkeypatch.setattr(cli, "BulkIngester", FakeBulkIngester)
    monkeypatch.setattr(cli.OpenSearchGateway, "from_aws", lambda **kwargs: gateway)
    monkeypatch.setattr(
        cli,
        "read_embedding_artifact",
        lambda **kwargs: {"synthetic_source_chunk_001": (0.0,) * 1024},
    )

    def fake_persist_receipt(context: Any, receipt: Any) -> Path:
        events.append(f"receipt:{receipt.status}")
        if fail_completed_receipt and receipt.status == "COMPLETED":
            raise OSError("synthetic final receipt failure")
        return tmp_path / "receipt.json"

    monkeypatch.setattr(cli, "_persist_receipt", fake_persist_receipt)


def test_ingest_persists_verified_receipt_before_alias_activation(
    tmp_path: Path, monkeypatch: Any
) -> None:
    context, _ = _ingest_context(tmp_path)
    events: list[str] = []
    gateway = FakeGateway(events)
    _patch_ingest_dependencies(
        monkeypatch,
        events=events,
        gateway=gateway,
        tmp_path=tmp_path,
    )

    summary = cli._ingest(context)

    assert events == [
        "bulk-verified",
        "receipt:VERIFIED_PENDING_ALIAS",
        "alias",
        "receipt:COMPLETED",
    ]
    assert summary["status"] == "COMPLETED"
    assert summary["production_approved"] is False


def test_alias_failure_deletes_new_index_and_persists_failed_receipt(
    tmp_path: Path, monkeypatch: Any
) -> None:
    context, _ = _ingest_context(tmp_path)
    events: list[str] = []
    gateway = FakeGateway(events, fail_alias=True)
    _patch_ingest_dependencies(
        monkeypatch,
        events=events,
        gateway=gateway,
        tmp_path=tmp_path,
    )

    with pytest.raises(RuntimeError, match="alias failure"):
        cli._ingest(context)

    assert events == [
        "bulk-verified",
        "receipt:VERIFIED_PENDING_ALIAS",
        "alias",
        "delete-index",
        "receipt:FAILED",
    ]


def test_final_receipt_failure_restores_alias_and_deletes_new_index(
    tmp_path: Path, monkeypatch: Any
) -> None:
    context, _ = _ingest_context(tmp_path)
    events: list[str] = []
    gateway = FakeGateway(events, alias_target_names=("old-staging-v1",))
    _patch_ingest_dependencies(
        monkeypatch,
        events=events,
        gateway=gateway,
        tmp_path=tmp_path,
        fail_completed_receipt=True,
    )

    with pytest.raises(OSError, match="final receipt failure"):
        cli._ingest(context)

    assert events == [
        "bulk-verified",
        "receipt:VERIFIED_PENDING_ALIAS",
        "alias",
        "receipt:COMPLETED",
        "restore-alias",
        "delete-index",
        "receipt:FAILED",
    ]


def test_multiple_preexisting_alias_targets_are_not_collapsed_to_first(
    tmp_path: Path, monkeypatch: Any
) -> None:
    context, _ = _ingest_context(tmp_path)
    events: list[str] = []
    gateway = FakeGateway(
        events,
        alias_target_names=("old-staging-a", "old-staging-b"),
    )
    _patch_ingest_dependencies(
        monkeypatch,
        events=events,
        gateway=gateway,
        tmp_path=tmp_path,
    )

    with pytest.raises(RuntimeError, match="multiple pre-existing targets"):
        cli._ingest(context)

    assert events == [
        "bulk-verified",
        "receipt:VERIFIED_PENDING_ALIAS",
        "delete-index",
        "receipt:FAILED",
    ]


def test_smoke_test_queries_verified_alias_not_concrete_index(
    tmp_path: Path, monkeypatch: Any
) -> None:
    context, _ = _ingest_context(tmp_path)
    events: list[str] = []
    gateway = FakeGateway(events, alias_target_names=("synthetic-staging-v1",))
    context.gateway = lambda: gateway
    definition = object()
    monkeypatch.setattr(cli, "_load_pipeline_definitions", lambda context: ())
    monkeypatch.setattr(cli, "load_smoke_test_definition", lambda path: definition)

    def fake_runtime_smoke(**kwargs: Any) -> AgentRuntimeSmokeReport:
        assert kwargs["base_url"] == "http://agent-runtime.test:8000"
        assert kwargs["definition"] is definition
        events.append("runtime-smoke")
        return AgentRuntimeSmokeReport(
            endpoint_path="/api/v1/rag/retrievals",
            positive_status="SUCCESS",
            positive_result_count=3,
            no_data_status="NO_DATA",
            no_data_result_count=0,
            no_data_fallback_present=True,
        )

    monkeypatch.setattr(cli, "run_agent_runtime_smoke", fake_runtime_smoke)

    summary = cli._smoke_test(context)

    assert events == ["smoke:synthetic-staging", "runtime-smoke"]
    assert summary["index_alias"] == "synthetic-staging"
    assert summary["scope"] == "bedrock_hybrid_retrieval_e2e"
    assert summary["production_approved"] is False


def test_cli_reports_bulk_error_classes_from_the_wrapped_cause(
    monkeypatch: Any, capsys: Any
) -> None:
    monkeypatch.setattr(cli, "_load_context", lambda args: object())

    def fail_ingest(context: Any) -> dict[str, Any]:
        try:
            raise BulkOperationError(
                "OpenSearch bulk create was not fully successful (synthetic_chunk_001)",
                error_types=("status_exception",),
            )
        except BulkOperationError as provider_exc:
            raise BulkIngestionError("ingestion failed: BulkOperationError") from provider_exc

    monkeypatch.setattr(cli, "_ingest", fail_ingest)

    assert cli.main(["ingest"]) == 1

    failure = json.loads(capsys.readouterr().err)
    assert failure["error_type"] == "BulkIngestionError"
    assert failure["failure_chain"] == ["BulkIngestionError", "BulkOperationError"]
    assert failure["dependency_bulk_error_types"] == ["status_exception"]
    assert "synthetic_chunk_001" not in json.dumps(failure)


def test_cli_reports_provider_error_code_without_the_provider_message(
    monkeypatch: Any, capsys: Any
) -> None:
    monkeypatch.setattr(cli, "_load_context", lambda args: object())

    class SyntheticClientError(RuntimeError):
        response = {"Error": {"Code": "ExpiredTokenException", "Message": "never belongs in a log"}}

    def fail_embeddings(context: Any) -> dict[str, Any]:
        try:
            raise SyntheticClientError("provider detail")
        except SyntheticClientError as provider_exc:
            raise EmbeddingBatchError(
                "embedding batch failed: SyntheticClientError",
                success_count=0,
                failure_count=262,
            ) from provider_exc

    monkeypatch.setattr(cli, "_generate_embeddings", fail_embeddings)

    assert cli.main(["generate-embeddings"]) == 1

    failure = json.loads(capsys.readouterr().err)
    assert failure["dependency_error_code"] == "ExpiredTokenException"
    assert failure["failure_chain"] == ["EmbeddingBatchError", "SyntheticClientError"]
    assert failure["embedding_failure_count"] == 262
    assert "never belongs in a log" not in json.dumps(failure)


def test_persist_receipt_retains_one_file_per_run(tmp_path: Path) -> None:
    manifest_path, chunks_dir = write_dataset(tmp_path / "dataset", effective=True)
    allowlist = load_allowlist(manifest_path)
    latest = tmp_path / "receipts" / "ingestion-receipt.json"

    class ReceiptSettings:
        rag_receipt_path = latest

    context = FakeContext(tmp_path / "repo", ReceiptSettings(), None)

    def make_receipt() -> Any:
        return new_receipt(
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

    first = make_receipt()
    cli._persist_receipt(context, first)
    first.complete("COMPLETED")
    cli._persist_receipt(context, first)
    second = make_receipt()
    second.complete("FAILED")
    cli._persist_receipt(context, second)

    retained = sorted(path.name for path in latest.parent.glob("ingestion-receipt-*.json"))
    assert retained == sorted(
        [
            f"ingestion-receipt-{first.run_id}.json",
            f"ingestion-receipt-{second.run_id}.json",
        ]
    )
    assert json.loads(latest.read_text(encoding="utf-8"))["run_id"] == second.run_id
    retained_first = latest.parent / f"ingestion-receipt-{first.run_id}.json"
    assert json.loads(retained_first.read_text(encoding="utf-8"))["status"] == "COMPLETED"


def test_run_receipt_path_rejects_a_run_id_that_could_escape_the_directory() -> None:
    with pytest.raises(ValueError, match="UUID"):
        cli._run_receipt_path(Path("receipts") / "ingestion-receipt.json", "../../secrets")


def test_missing_agent_runtime_url_fails_before_opensearch_initialization(
    tmp_path: Path, monkeypatch: Any
) -> None:
    context, _ = _ingest_context(tmp_path)
    gateway_calls: list[str] = []
    context.gateway = lambda: gateway_calls.append("opensearch")

    def missing_base_url() -> str:
        raise SettingsError("AGENT_RUNTIME_BASE_URL is required")

    context.settings.require_agent_runtime_base_url = missing_base_url
    monkeypatch.setattr(cli, "load_smoke_test_definition", lambda path: object())

    with pytest.raises(SettingsError, match="AGENT_RUNTIME_BASE_URL"):
        cli._smoke_test(context)

    assert gateway_calls == []
