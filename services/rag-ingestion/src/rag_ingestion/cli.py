"""Command-line entrypoint used by the repository's six thin RAG scripts."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from opensearchpy.exceptions import RequestError

from rag_ingestion.allowlist import Allowlist, ExecutionGovernance, load_allowlist
from rag_ingestion.bedrock_embedder import (
    BedrockEmbedder,
    generate_embedding_artifact,
    read_embedding_artifact,
)
from rag_ingestion.bulk_ingester import BulkIngester
from rag_ingestion.chunk_loader import load_allowlisted_chunks
from rag_ingestion.index_manager import (
    IndexConfigurationError,
    IndexManager,
    load_index_definition,
    load_search_pipeline_definition,
)
from rag_ingestion.opensearch_client import OpenSearchGateway
from rag_ingestion.receipt import new_receipt, write_receipt
from rag_ingestion.settings import IngestionSettings, SettingsError, load_settings
from rag_ingestion.smoke_test import (
    SmokeTestError,
    load_smoke_test_definition,
    run_agent_runtime_smoke,
)
from rag_ingestion.validator import ValidationResult, validate_chunks

COMMANDS = (
    "validate-allowlist",
    "create-index",
    "generate-embeddings",
    "ingest",
    "verify-index",
    "smoke-test",
)
DIAGNOSTIC_COMMANDS = ("inspect-pipelines",)
_MAX_DEPENDENCY_REASON_LENGTH = 512
_RUN_ID_PATTERN = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
_LOCAL_CONFIGURATION_ERROR_TYPES = (IndexConfigurationError, SettingsError, SmokeTestError)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    context: _Context | None = None
    try:
        context = _load_context(args)
        handlers = {
            "validate-allowlist": _validate_allowlist,
            "create-index": _create_index,
            "generate-embeddings": _generate_embeddings,
            "ingest": _ingest,
            "verify-index": _verify_index,
            "smoke-test": _smoke_test,
            "inspect-pipelines": _inspect_pipelines,
        }
        summary = handlers[args.command](context)
        _print_json(summary)
        return 0
    except Exception as exc:
        failure_summary: dict[str, Any] = {
            "status": "FAILED",
            "command": getattr(args, "command", "unknown"),
            "error_type": type(exc).__name__,
        }
        chain = _exception_chain(exc)
        failure_summary["failure_chain"] = [type(item).__name__ for item in chain]
        for field_name in ("success_count", "failure_count"):
            count = getattr(exc, field_name, None)
            if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
                failure_summary[f"embedding_{field_name}"] = count
        dependency_status_code = _first_in_chain(chain, "status_code", _is_http_error_status)
        if dependency_status_code is not None:
            failure_summary["dependency_status_code"] = dependency_status_code
        dependency_error = _first_in_chain(chain, "error", _is_safe_dependency_token)
        if dependency_error is not None:
            failure_summary["dependency_error"] = dependency_error
        dependency_error_code = _safe_provider_error_code(chain)
        if dependency_error_code is not None:
            failure_summary["dependency_error_code"] = dependency_error_code
        bulk_error_types = _safe_bulk_error_types(chain)
        if bulk_error_types:
            failure_summary["dependency_bulk_error_types"] = bulk_error_types
        dependency_reason = _safe_create_index_dependency_reason(
            command=getattr(args, "command", "unknown"),
            exc=exc,
        )
        if dependency_reason is not None:
            failure_summary["dependency_reason"] = dependency_reason
        failure_reason = _safe_local_configuration_failure_reason(exc)
        if failure_reason is not None:
            failure_summary["failure_reason"] = failure_reason
        missing_module = getattr(exc, "name", None)
        if isinstance(exc, ModuleNotFoundError) and isinstance(missing_module, str):
            if all(part.isidentifier() for part in missing_module.split(".")):
                failure_summary["missing_module"] = missing_module
        governance_status = getattr(exc, "governance_status", None)
        production_approved = getattr(exc, "production_approved", None)
        decision = getattr(context, "last_governance_decision", None)
        if governance_status is None and decision is not None:
            governance_status = decision.governance_status
        if production_approved is None and decision is not None:
            production_approved = decision.production_approved
        if isinstance(governance_status, str):
            failure_summary["governance_status"] = governance_status
        if isinstance(production_approved, bool):
            failure_summary["production_approved"] = production_approved
        _print_json(
            failure_summary,
            stream=sys.stderr,
        )
        return 1


class _Context:
    def __init__(
        self,
        *,
        repository_root: Path,
        settings: IngestionSettings,
        index_config_path: Path,
        natural_pipeline_path: Path,
        legal_pipeline_path: Path,
        smoke_config_path: Path,
    ) -> None:
        self.repository_root = repository_root
        self.settings = settings
        self.index_config_path = index_config_path
        self.natural_pipeline_path = natural_pipeline_path
        self.legal_pipeline_path = legal_pipeline_path
        self.smoke_config_path = smoke_config_path
        self.last_governance_decision: ExecutionGovernance | None = None

    def validate(self) -> tuple[Allowlist, ValidationResult]:
        allowlist_path, chunks_dir = self.settings.require_paths()
        allowlist = load_allowlist(allowlist_path)
        loaded = load_allowlisted_chunks(chunks_dir, allowlist)
        return allowlist, validate_chunks(loaded, allowlist)

    def gateway(self) -> OpenSearchGateway:
        region, host, _, _ = self.settings.require_opensearch()
        return OpenSearchGateway.from_aws(host=host, region=region)


def _validate_allowlist(context: _Context) -> dict[str, Any]:
    allowlist, validation = context.validate()
    decision = _execution_governance(context, allowlist)
    return {
        "status": "VALID",
        "execution_allowed": decision.execution_allowed,
        **_governance_log_fields(decision),
        "source_count": validation.source_count,
        "allowlist_chunk_count": allowlist.declared_chunk_count,
        "validated_chunk_count": validation.chunk_count,
        "allowlist_sha256": allowlist.sha256,
        "governance": {
            **allowlist.governance.to_receipt_dict(),
            **_governance_log_fields(decision),
            "blocking_reasons": list(decision.blocking_reasons),
        },
    }


def _create_index(context: _Context) -> dict[str, Any]:
    allowlist, validation = context.validate()
    decision = _assert_allowlist_execution(context, allowlist)
    _, _, index_name, alias_name = context.settings.require_opensearch()
    definition = load_index_definition(context.index_config_path)
    definition = replace(
        definition,
        configured_name=index_name,
        configured_alias=alias_name,
    )
    gateway = context.gateway()
    pipelines = (
        load_search_pipeline_definition(context.natural_pipeline_path),
        load_search_pipeline_definition(context.legal_pipeline_path),
    )
    IndexManager(gateway).create_staging_resources(index_name, definition, pipelines)
    return {
        "status": "CREATED",
        **_governance_log_fields(decision),
        "index_name": index_name,
        "index_alias": alias_name,
        "vector_dimension": definition.vector_dimension,
        "validated_chunk_count": validation.chunk_count,
        "search_pipelines": [
            {
                "name": pipeline.name,
                "bm25_weight": pipeline.bm25_weight,
                "vector_weight": pipeline.vector_weight,
            }
            for pipeline in pipelines
        ],
    }


def _inspect_pipelines(context: _Context) -> dict[str, Any]:
    """Inspect configured staging pipelines without mutating any resource."""

    allowlist, _ = context.validate()
    decision = _assert_allowlist_execution(context, allowlist)
    inspections = IndexManager(context.gateway()).inspect_search_pipelines(
        _load_pipeline_definitions(context)
    )
    return {
        "status": "INSPECTED",
        **_governance_log_fields(decision),
        "search_pipelines": [
            {
                "name": inspection.name,
                "status": inspection.status,
                "config_match": inspection.config_match,
            }
            for inspection in inspections
        ],
    }


def _generate_embeddings(context: _Context) -> dict[str, Any]:
    allowlist, validation = context.validate()
    decision = _assert_allowlist_execution(context, allowlist)
    region, model_id, dimension = context.settings.require_bedrock()
    artifact_path = context.settings.embedding_artifact_path(context.repository_root)
    embedder = BedrockEmbedder.from_boto3(
        region=region,
        model_id=model_id,
        dimension=dimension,
        batch_size=context.settings.embedding_batch_size,
        truncate=context.settings.embedding_truncate,
    )
    result = generate_embedding_artifact(
        allowlist=allowlist,
        expected_allowlist_sha256=context.settings.rag_allowlist_expected_sha256,
        rag_mode=context.settings.rag_mode,
        require_owner_signature=context.settings.rag_require_owner_signature,
        production_enabled=context.settings.rag_production_enabled,
        embedder=embedder,
        chunks=validation.chunks,
        artifact_path=artifact_path,
        repository_root=context.repository_root,
    )
    return {
        "status": "EMBEDDED",
        **_governance_log_fields(decision),
        "embedding_model_id": model_id,
        "embedding_dimension": dimension,
        "embedding_success_count": result.success_count,
        "embedding_failure_count": result.failure_count,
        "artifact_location": "external_temp",
    }


def _ingest(context: _Context) -> dict[str, Any]:
    allowlist, validation = context.validate()
    decision = _assert_allowlist_execution(context, allowlist)
    region, host, index_name, alias_name = context.settings.require_opensearch()
    model_id = context.settings.bedrock_embedding_model_id or ""
    dimension = context.settings.bedrock_embedding_dimension
    artifact_path = context.settings.embedding_artifact_path(context.repository_root)
    vectors = read_embedding_artifact(
        allowlist=allowlist,
        model_id=model_id,
        artifact_path=artifact_path,
        repository_root=context.repository_root,
        chunks=validation.chunks,
        dimension=dimension,
    )
    receipt = new_receipt(
        allowlist=allowlist,
        chunks_dir=context.settings.require_paths()[1],
        model_id=model_id,
        dimension=dimension,
        index_name=index_name,
        index_alias=alias_name,
        mode=context.settings.rag_mode,
        expected_allowlist_sha256=context.settings.rag_allowlist_expected_sha256,
        require_owner_signature=context.settings.rag_require_owner_signature,
        production_enabled=context.settings.rag_production_enabled,
        repository_root=context.repository_root,
    )
    receipt.validated_chunk_count = validation.chunk_count
    receipt.embedding_success_count = len(vectors)
    gateway = OpenSearchGateway.from_aws(host=host, region=region)
    try:
        report = BulkIngester(gateway, dimension=dimension).ingest(
            index_name=index_name,
            alias_name=alias_name,
            chunks=validation.chunks,
            vectors=vectors,
            activate_alias=False,
        )
    except Exception as exc:
        receipt.errors.append(type(exc).__name__)
        receipt.complete("FAILED")
        _persist_receipt(context, receipt)
        raise
    receipt.indexed_document_count = report.indexed_document_count
    receipt.duplicate_id_count = report.duplicate_id_count
    receipt.mark_verified_pending_alias()
    try:
        receipt_path = _persist_receipt(context, receipt)
    except Exception:
        gateway.delete_index(index_name)
        raise
    previous_alias_targets: tuple[str, ...] = ()
    alias_update_attempted = False
    try:
        previous_alias_targets = gateway.alias_targets(alias_name)
        if len(previous_alias_targets) > 1:
            raise RuntimeError("staging alias has multiple pre-existing targets")
        alias_update_attempted = True
        IndexManager(gateway).activate_alias(index_name, alias_name)
    except Exception as exc:
        receipt.errors.append(type(exc).__name__)
        _rollback_alias_cutover(
            gateway,
            index_name=index_name,
            alias_name=alias_name,
            previous_alias_targets=previous_alias_targets,
            restore_previous_alias=alias_update_attempted,
            receipt=receipt,
        )
        receipt.complete("FAILED")
        try:
            _persist_receipt(context, receipt)
        except Exception as receipt_exc:
            receipt.errors.append(type(receipt_exc).__name__)
        raise
    receipt.complete("COMPLETED")
    try:
        receipt_path = _persist_receipt(context, receipt)
    except Exception as exc:
        receipt.errors.append(type(exc).__name__)
        _rollback_alias_cutover(
            gateway,
            index_name=index_name,
            alias_name=alias_name,
            previous_alias_targets=previous_alias_targets,
            restore_previous_alias=True,
            receipt=receipt,
        )
        receipt.complete("FAILED")
        try:
            _persist_receipt(context, receipt)
        except Exception as receipt_exc:
            receipt.errors.append(type(receipt_exc).__name__)
        raise
    return {
        **receipt.to_dict(),
        **_governance_log_fields(decision),
        "receipt_location": _safe_receipt_location(receipt_path, context.repository_root),
    }


def _verify_index(context: _Context) -> dict[str, Any]:
    allowlist, validation = context.validate()
    decision = _assert_allowlist_execution(context, allowlist)
    _, _, index_name, alias_name = context.settings.require_opensearch()
    gateway = context.gateway()
    manager = IndexManager(gateway)
    manager.verify_mapping_dimension(index_name, context.settings.bedrock_embedding_dimension)
    pipelines = _load_pipeline_definitions(context)
    manager.verify_search_pipelines(pipelines)
    manager.verify_alias(index_name, alias_name)
    report = BulkIngester(gateway, dimension=context.settings.bedrock_embedding_dimension).verify(
        index_name=index_name,
        expected_ids=[chunk.chunk_id for chunk in validation.chunks],
        expected_count=allowlist.declared_chunk_count,
    )
    return {
        "status": "VERIFIED",
        **_governance_log_fields(decision),
        "index_name": index_name,
        "index_alias": alias_name,
        "indexed_document_count": report.indexed_document_count,
        "duplicate_id_count": report.duplicate_id_count,
        "embedding_dimension": report.vector_dimension,
        "search_pipelines": [pipeline.name for pipeline in pipelines],
        "alias_verified": True,
    }


def _smoke_test(context: _Context) -> dict[str, Any]:
    allowlist, _ = context.validate()
    decision = _assert_allowlist_execution(context, allowlist)
    smoke_definition = load_smoke_test_definition(context.smoke_config_path)
    agent_runtime_base_url = context.settings.require_agent_runtime_base_url()
    _, _, index_name, alias_name = context.settings.require_opensearch()
    gateway = context.gateway()
    manager = IndexManager(gateway)
    pipelines = _load_pipeline_definitions(context)
    manager.verify_search_pipelines(pipelines)
    manager.verify_alias(index_name, alias_name)
    hit_count = gateway.smoke_test_current_normal_rag(alias_name)
    runtime_report = run_agent_runtime_smoke(
        base_url=agent_runtime_base_url,
        definition=smoke_definition,
    )
    return {
        "status": "PASSED",
        **_governance_log_fields(decision),
        "index_name": index_name,
        "index_alias": alias_name,
        "safe_filtered_hit_count": hit_count,
        "filters": {"current_status": "current", "stop_normal_rag": False},
        "search_pipelines": [pipeline.name for pipeline in pipelines],
        "runtime_endpoint_path": runtime_report.endpoint_path,
        "positive_retrieval": {
            "status": runtime_report.positive_status,
            "result_count": runtime_report.positive_result_count,
        },
        "no_data_retrieval": {
            "status": runtime_report.no_data_status,
            "result_count": runtime_report.no_data_result_count,
            "fallback_present": runtime_report.no_data_fallback_present,
        },
        "scope": "bedrock_hybrid_retrieval_e2e",
    }


def _load_context(args: argparse.Namespace) -> _Context:
    repository_root = Path(args.repository_root).expanduser().resolve()
    config_dir_value = args.config_dir or os.getenv("RAG_CONFIG_DIR")
    config_dir = (
        Path(config_dir_value).expanduser().resolve()
        if config_dir_value
        else repository_root / "config" / "rag"
    )
    bootstrap_settings = IngestionSettings()
    embedding_path = _configured_path(
        bootstrap_settings.rag_embedding_config_path,
        config_dir / "embedding.yaml",
        repository_root,
    )
    index_path = _configured_path(
        bootstrap_settings.rag_opensearch_index_config_path,
        config_dir / "opensearch-index-v1.json",
        repository_root,
    )
    natural_pipeline_path = _configured_path(
        bootstrap_settings.rag_hybrid_natural_config_path,
        config_dir / "hybrid-natural-language.json",
        repository_root,
    )
    legal_pipeline_path = _configured_path(
        bootstrap_settings.rag_hybrid_legal_config_path,
        config_dir / "hybrid-legal.json",
        repository_root,
    )
    staging_path = _configured_path(
        bootstrap_settings.rag_staging_filters_config_path,
        config_dir / "staging-filters.yaml",
        repository_root,
    )
    smoke_path = _configured_path(
        bootstrap_settings.rag_smoke_config_path,
        config_dir / "smoke-test.yaml",
        repository_root,
    )
    settings = load_settings(
        embedding_config_path=embedding_path,
        index_config_path=index_path,
        staging_config_path=staging_path,
        repository_root=repository_root,
    )
    return _Context(
        repository_root=repository_root,
        settings=settings,
        index_config_path=index_path,
        natural_pipeline_path=natural_pipeline_path,
        legal_pipeline_path=legal_pipeline_path,
        smoke_config_path=smoke_path,
    )


def _configured_path(configured: Path | None, default: Path, repository_root: Path) -> Path:
    if not configured:
        return default
    path = configured.expanduser()
    return path.resolve() if path.is_absolute() else (repository_root / path).resolve()


def _persist_receipt(context: _Context, receipt: Any) -> Path:
    path = context.settings.rag_receipt_path or (
        Path(tempfile.gettempdir()) / "kinsun-rag" / "ingestion-receipt.json"
    )
    # The per-run file is written first so a failure to refresh the rolling
    # latest receipt cannot leave the run with no evidence at all.
    write_receipt(receipt, _run_receipt_path(path, receipt.run_id))
    write_receipt(receipt, path)
    return path.resolve()


def _run_receipt_path(path: Path, run_id: str) -> Path:
    """Name the retained per-run receipt beside the rolling latest one.

    Repeated writes within a run share a run_id and update the same file, so
    the retained copy tracks that run's final state rather than accumulating
    partial snapshots.
    """

    if not isinstance(run_id, str) or not _RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("run_id must be a UUID before it can name a receipt file")
    return path.with_name(f"{path.stem}-{run_id}{path.suffix}")


def _rollback_alias_cutover(
    gateway: OpenSearchGateway,
    *,
    index_name: str,
    alias_name: str,
    previous_alias_targets: tuple[str, ...],
    restore_previous_alias: bool,
    receipt: Any,
) -> None:
    if restore_previous_alias and len(previous_alias_targets) == 1:
        try:
            gateway.set_alias(previous_alias_targets[0], alias_name)
        except Exception as restore_exc:
            receipt.errors.append(type(restore_exc).__name__)
    try:
        # Deleting the new index also removes any alias when there was no prior target.
        gateway.delete_index(index_name)
    except Exception as rollback_exc:
        receipt.errors.append(type(rollback_exc).__name__)


def _load_pipeline_definitions(context: _Context) -> tuple[Any, Any]:
    return (
        load_search_pipeline_definition(context.natural_pipeline_path),
        load_search_pipeline_definition(context.legal_pipeline_path),
    )


def _execution_governance(context: _Context, allowlist: Allowlist) -> ExecutionGovernance:
    decision = allowlist.execution_governance(
        context.settings.rag_allowlist_expected_sha256,
        mode=context.settings.rag_mode,
        require_owner_signature=context.settings.rag_require_owner_signature,
        production_enabled=context.settings.rag_production_enabled,
    )
    context.last_governance_decision = decision
    return decision


def _assert_allowlist_execution(context: _Context, allowlist: Allowlist) -> ExecutionGovernance:
    decision = allowlist.assert_effective_for_execution(
        context.settings.rag_allowlist_expected_sha256,
        mode=context.settings.rag_mode,
        require_owner_signature=context.settings.rag_require_owner_signature,
        production_enabled=context.settings.rag_production_enabled,
    )
    context.last_governance_decision = decision
    context.settings.assert_staging_only_external_execution()
    return decision


def _governance_log_fields(decision: ExecutionGovernance) -> dict[str, Any]:
    return {
        "governance_status": decision.governance_status,
        "production_approved": decision.production_approved,
    }


def _safe_receipt_location(path: Path, repository_root: Path) -> str:
    try:
        return str(path.relative_to(repository_root))
    except ValueError:
        return "external_temp"


def _safe_create_index_dependency_reason(*, command: str, exc: Exception) -> str | None:
    """Return a bounded schema diagnostic only for create-index RequestErrors.

    Bulk and retrieval errors can contain indexed source fragments, so their provider
    details must never enter the command's JSON logs.
    """

    if command != "create-index" or not isinstance(exc, RequestError):
        return None
    info = getattr(exc, "info", None)
    if not isinstance(info, dict):
        return None
    error = info.get("error")
    if not isinstance(error, dict):
        return None

    candidates: list[object] = [error.get("reason")]
    root_cause = error.get("root_cause")
    if isinstance(root_cause, list):
        candidates.extend(cause.get("reason") for cause in root_cause if isinstance(cause, dict))
    for candidate in candidates:
        if _is_safe_dependency_reason(candidate):
            return candidate
    return None


def _is_safe_dependency_reason(value: object) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= _MAX_DEPENDENCY_REASON_LENGTH
        and value.isprintable()
    )


def _exception_chain(exc: BaseException, *, limit: int = 6) -> list[BaseException]:
    """Walk `raise ... from ...` links so wrapped provider failures stay visible.

    Every adapter re-raises its own error type, so the outermost exception alone
    reports `BulkIngestionError` and nothing about what the provider refused.
    """

    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and len(chain) < limit and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__
    return chain


def _first_in_chain(
    chain: Sequence[BaseException], attribute: str, predicate: Callable[[Any], bool]
) -> Any | None:
    for item in chain:
        value = getattr(item, attribute, None)
        if predicate(value):
            return value
    return None


def _is_http_error_status(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 400 <= value <= 599


def _is_safe_dependency_token(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= 128
        and all(character.isalnum() or character in "._:- " for character in value)
    )


def _safe_provider_error_code(chain: Sequence[BaseException]) -> str | None:
    """Return a botocore error code, which is symbolic and carries no payload."""

    for item in chain:
        response = getattr(item, "response", None)
        error = response.get("Error") if isinstance(response, dict) else None
        code = error.get("Code") if isinstance(error, dict) else None
        if isinstance(code, str) and code.isidentifier():
            return code
    return None


def _safe_bulk_error_types(chain: Sequence[BaseException]) -> list[str]:
    """Return OpenSearch item error classes, never their reason text."""

    for item in chain:
        error_types = getattr(item, "error_types", None)
        if isinstance(error_types, tuple):
            return [
                error_type
                for error_type in error_types[:5]
                if isinstance(error_type, str) and error_type.isidentifier()
            ]
    return []


def _safe_local_configuration_failure_reason(exc: Exception) -> str | None:
    """Return a bounded message only for locally controlled configuration errors.

    Provider, bulk-ingestion, and Bedrock exception messages can include remote
    payload data.  Keep those messages out of the command JSON entirely.
    """

    if type(exc) not in _LOCAL_CONFIGURATION_ERROR_TYPES:
        return None
    reason = str(exc)
    if _is_safe_dependency_reason(reason):
        return reason
    return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="kinsun.ai staging RAG ingestion")
    parser.add_argument("command", choices=(*COMMANDS, *DIAGNOSTIC_COMMANDS))
    parser.add_argument("--repository-root", default=str(Path.cwd()))
    parser.add_argument("--config-dir")
    return parser


def _print_json(payload: dict[str, Any], *, stream: Any = sys.stdout) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=stream)


if __name__ == "__main__":
    raise SystemExit(main())
