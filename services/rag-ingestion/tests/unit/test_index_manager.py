from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from rag_ingestion.index_manager import (
    RESOURCE_VISIBILITY_ATTEMPTS,
    IndexConfigurationError,
    IndexManager,
    load_index_definition,
    load_search_pipeline_definition,
)


class FakeIndexClient:
    def __init__(self, *, exists: bool = False, dimension: int = 1024) -> None:
        self.exists = exists
        self.dimension = dimension
        self.created: list[tuple[str, dict[str, Any]]] = []
        self.aliases: list[tuple[str, str]] = []
        self.pipelines: dict[str, dict[str, Any]] = {}
        self.deleted_indexes: list[str] = []
        self.deleted_pipelines: list[str] = []
        self.pipeline_gets: list[str] = []
        self.pipeline_puts: list[str] = []
        self.pipeline_operations: list[tuple[str, str]] = []
        self.fail_pipeline: str | None = None
        self.alias_target_names: tuple[str, ...] = ()
        self.mapping_read_responses: list[dict[str, Any] | Exception] = []
        self.pipeline_visibility_delays: dict[str, int] = {}

    def index_exists(self, index_name: str) -> bool:
        return self.exists

    def create_index(self, index_name: str, body: dict[str, Any]) -> None:
        self.created.append((index_name, body))

    def delete_index(self, index_name: str) -> None:
        self.deleted_indexes.append(index_name)

    def get_mapping(self, index_name: str) -> dict[str, Any]:
        if self.mapping_read_responses:
            response = self.mapping_read_responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
        return {
            index_name: {
                "mappings": {
                    "properties": {"embedding": {"type": "knn_vector", "dimension": self.dimension}}
                }
            }
        }

    def set_alias(self, index_name: str, alias_name: str) -> None:
        self.aliases.append((index_name, alias_name))

    def alias_targets(self, alias_name: str) -> tuple[str, ...]:
        return self.alias_target_names

    def get_search_pipeline(self, pipeline_name: str) -> dict[str, Any] | None:
        self.pipeline_gets.append(pipeline_name)
        self.pipeline_operations.append(("get", pipeline_name))
        remaining_reads = self.pipeline_visibility_delays.get(pipeline_name, 0)
        if pipeline_name in self.pipelines and remaining_reads:
            self.pipeline_visibility_delays[pipeline_name] = remaining_reads - 1
            return None
        return self.pipelines.get(pipeline_name)

    def put_search_pipeline(self, pipeline_name: str, body: dict[str, Any]) -> None:
        self.pipeline_puts.append(pipeline_name)
        self.pipeline_operations.append(("put", pipeline_name))
        if pipeline_name == self.fail_pipeline:
            raise RuntimeError("synthetic failed acknowledgement")
        self.pipelines[pipeline_name] = body

    def delete_search_pipeline(self, pipeline_name: str) -> None:
        self.deleted_pipelines.append(pipeline_name)
        self.pipelines.pop(pipeline_name, None)


class SyntheticNotFoundError(RuntimeError):
    status_code = 404


def _write_config(
    path: Path,
    *,
    dimension: int = 1024,
    mode: str = "staging",
    vector_type: str = "knn_vector",
    space_type: str = "cosinesimil",
    method_name: str = "hnsw",
    method_extra: dict[str, Any] | None = None,
) -> None:
    method = {"name": method_name}
    if method_extra:
        method.update(method_extra)
    path.write_text(
        json.dumps(
            {
                "mode": mode,
                "index": {"name": "synthetic-staging-v1", "alias": "synthetic-staging"},
                "settings": {"index": {"knn": True}},
                "mappings": {
                    "properties": {
                        "embedding": {
                            "type": vector_type,
                            "dimension": dimension,
                            "space_type": space_type,
                            "method": method,
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def _write_pipeline(
    path: Path,
    *,
    profile: str,
    name: str,
    bm25: float,
    vector: float,
) -> None:
    path.write_text(
        json.dumps(
            {
                "profile": profile,
                "search_pipeline": name,
                "bm25_weight": bm25,
                "vector_weight": vector,
                "pipeline": {
                    "description": "synthetic",
                    "phase_results_processors": [
                        {
                            "normalization-processor": {
                                "normalization": {"technique": "min_max"},
                                "combination": {
                                    "technique": "arithmetic_mean",
                                    "parameters": {"weights": [bm25, vector]},
                                },
                            }
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )


def test_create_fresh_staging_index_and_verify_mapping(tmp_path: Path) -> None:
    config_path = tmp_path / "index.json"
    _write_config(config_path)
    definition = load_index_definition(config_path)
    client = FakeIndexClient()

    IndexManager(client).create_staging_index("synthetic-staging-v1", definition)

    assert client.created[0][0] == "synthetic-staging-v1"


def test_nextgen_index_config_rejects_method_engine(tmp_path: Path) -> None:
    config_path = tmp_path / "index.json"
    _write_config(config_path, method_extra={"engine": "faiss"})

    with pytest.raises(IndexConfigurationError, match="must not set method.engine"):
        load_index_definition(config_path)


@pytest.mark.parametrize(
    "missing_path",
    [
        ("type",),
        ("dimension",),
        ("space_type",),
        ("method",),
        ("method", "name"),
    ],
)
def test_nextgen_index_config_rejects_missing_required_vector_mapping(
    tmp_path: Path, missing_path: tuple[str, ...]
) -> None:
    config_path = tmp_path / "index.json"
    _write_config(config_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    embedding = config["mappings"]["properties"]["embedding"]
    target = embedding
    for key in missing_path[:-1]:
        target = target[key]
    del target[missing_path[-1]]
    config_path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(IndexConfigurationError):
        load_index_definition(config_path)


@pytest.mark.parametrize(
    ("vector_type", "dimension", "space_type", "method_name"),
    [
        ("text", 1024, "cosinesimil", "hnsw"),
        ("knn_vector", 1536, "cosinesimil", "hnsw"),
        ("knn_vector", 1024, "l2", "hnsw"),
        ("knn_vector", 1024, "cosinesimil", "ivf"),
    ],
)
def test_nextgen_index_config_rejects_invalid_required_vector_mapping(
    tmp_path: Path,
    vector_type: str,
    dimension: int,
    space_type: str,
    method_name: str,
) -> None:
    config_path = tmp_path / "index.json"
    _write_config(
        config_path,
        vector_type=vector_type,
        dimension=dimension,
        space_type=space_type,
        method_name=method_name,
    )

    with pytest.raises(IndexConfigurationError):
        load_index_definition(config_path)


def test_checked_in_nextgen_index_config_uses_engine_free_mapping() -> None:
    repository_root = Path(__file__).resolve().parents[4]

    definition = load_index_definition(repository_root / "config/rag/opensearch-index-v1.json")

    embedding_mapping = definition.body["mappings"]["properties"]["embedding"]
    assert embedding_mapping == {
        "type": "knn_vector",
        "dimension": 1024,
        "space_type": "cosinesimil",
        "method": {"name": "hnsw"},
    }


def test_existing_index_is_not_overwritten(tmp_path: Path) -> None:
    config_path = tmp_path / "index.json"
    _write_config(config_path)

    with pytest.raises(IndexConfigurationError, match="already exists"):
        IndexManager(FakeIndexClient(exists=True)).create_staging_index(
            "synthetic-staging-v1", load_index_definition(config_path)
        )


def test_mapping_readback_failure_rolls_back_new_index(tmp_path: Path) -> None:
    config_path = tmp_path / "index.json"
    _write_config(config_path)
    client = FakeIndexClient(dimension=1536)

    with pytest.raises(IndexConfigurationError, match="expected 1024"):
        IndexManager(client).create_staging_index(
            "synthetic-staging-v1", load_index_definition(config_path)
        )

    assert client.deleted_indexes == ["synthetic-staging-v1"]


def test_mapping_verification_retries_a_transient_not_found(tmp_path: Path) -> None:
    config_path = tmp_path / "index.json"
    _write_config(config_path)
    client = FakeIndexClient()
    client.mapping_read_responses.append(SyntheticNotFoundError("not ready"))
    waits: list[float] = []

    IndexManager(client, sleeper=waits.append).create_staging_index(
        "synthetic-staging-v1", load_index_definition(config_path)
    )

    assert waits == [5.0]
    assert client.deleted_indexes == []


def test_non_staging_config_is_rejected_when_creating_staging_index(tmp_path: Path) -> None:
    config_path = tmp_path / "index.json"
    _write_config(config_path, mode="production")
    definition = load_index_definition(config_path)

    with pytest.raises(IndexConfigurationError):
        IndexManager(FakeIndexClient()).create_staging_index("synthetic-staging-v1", definition)


def test_search_pipeline_names_and_weights_are_loaded_and_provisioned(tmp_path: Path) -> None:
    index_path = tmp_path / "index.json"
    natural_path = tmp_path / "natural.json"
    legal_path = tmp_path / "legal.json"
    _write_config(index_path)
    _write_pipeline(
        natural_path,
        profile="natural_language",
        name="synthetic-natural-staging-v1",
        bm25=0.4,
        vector=0.6,
    )
    _write_pipeline(
        legal_path,
        profile="legal",
        name="synthetic-legal-staging-v1",
        bm25=0.65,
        vector=0.35,
    )
    pipelines = (
        load_search_pipeline_definition(natural_path),
        load_search_pipeline_definition(legal_path),
    )
    client = FakeIndexClient()

    IndexManager(client).create_staging_resources(
        "synthetic-staging-v1", load_index_definition(index_path), pipelines
    )

    assert pipelines[0].bm25_weight == 0.4
    assert pipelines[0].vector_weight == 0.6
    assert pipelines[1].bm25_weight == 0.65
    assert pipelines[1].vector_weight == 0.35
    assert set(client.pipelines) == {
        "synthetic-natural-staging-v1",
        "synthetic-legal-staging-v1",
    }


def test_pipeline_provider_failure_is_not_converted_to_a_local_failure_reason(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "index.json"
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    _write_config(index_path)
    _write_pipeline(
        first_path,
        profile="natural_language",
        name="synthetic-natural-staging-v1",
        bm25=0.4,
        vector=0.6,
    )
    _write_pipeline(
        second_path,
        profile="legal",
        name="synthetic-legal-staging-v1",
        bm25=0.65,
        vector=0.35,
    )
    client = FakeIndexClient()
    client.fail_pipeline = "synthetic-legal-staging-v1"

    with pytest.raises(RuntimeError, match="synthetic failed acknowledgement"):
        IndexManager(client).create_staging_resources(
            "synthetic-staging-v1",
            load_index_definition(index_path),
            (
                load_search_pipeline_definition(first_path),
                load_search_pipeline_definition(second_path),
            ),
        )

    assert client.created == []
    assert client.deleted_indexes == []
    assert client.deleted_pipelines == []
    assert "synthetic-natural-staging-v1" in client.pipelines


def test_search_pipeline_verification_retries_until_resource_is_visible(tmp_path: Path) -> None:
    index_path = tmp_path / "index.json"
    pipeline_path = tmp_path / "natural.json"
    _write_config(index_path)
    _write_pipeline(
        pipeline_path,
        profile="natural_language",
        name="synthetic-natural-staging-v1",
        bm25=0.4,
        vector=0.6,
    )
    pipeline = load_search_pipeline_definition(pipeline_path)
    client = FakeIndexClient()
    client.pipeline_visibility_delays[pipeline.name] = 2
    waits: list[float] = []

    IndexManager(client, sleeper=waits.append).create_staging_resources(
        "synthetic-staging-v1", load_index_definition(index_path), (pipeline,)
    )

    assert waits == [5.0, 5.0]
    assert client.deleted_indexes == []
    assert client.deleted_pipelines == []


def test_search_pipeline_visibility_timeout_retains_pipeline_and_does_not_create_index(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "index.json"
    pipeline_path = tmp_path / "natural.json"
    _write_config(index_path)
    _write_pipeline(
        pipeline_path,
        profile="natural_language",
        name="synthetic-natural-staging-v1",
        bm25=0.4,
        vector=0.6,
    )
    pipeline = load_search_pipeline_definition(pipeline_path)
    client = FakeIndexClient()
    client.pipeline_visibility_delays[pipeline.name] = 10
    waits: list[float] = []

    with pytest.raises(
        IndexConfigurationError,
        match="verification timed out.*retained for safe reconciliation",
    ):
        IndexManager(client, sleeper=waits.append, visibility_attempts=3).create_staging_resources(
            "synthetic-staging-v1", load_index_definition(index_path), (pipeline,)
        )

    assert waits == [5.0, 5.0]
    assert client.deleted_pipelines == []
    assert client.created == []
    assert client.deleted_indexes == []


def test_pipeline_verification_polls_all_pending_pipelines_in_one_window(tmp_path: Path) -> None:
    index_path = tmp_path / "index.json"
    natural_path = tmp_path / "natural.json"
    legal_path = tmp_path / "legal.json"
    _write_config(index_path)
    _write_pipeline(
        natural_path,
        profile="natural_language",
        name="synthetic-natural-staging-v1",
        bm25=0.4,
        vector=0.6,
    )
    _write_pipeline(
        legal_path,
        profile="legal",
        name="synthetic-legal-staging-v1",
        bm25=0.65,
        vector=0.35,
    )
    pipelines = (
        load_search_pipeline_definition(natural_path),
        load_search_pipeline_definition(legal_path),
    )
    client = FakeIndexClient()
    client.pipeline_visibility_delays[pipelines[0].name] = 2
    client.pipeline_visibility_delays[pipelines[1].name] = 3
    waits: list[float] = []

    IndexManager(client, sleeper=waits.append).create_staging_resources(
        "synthetic-staging-v1", load_index_definition(index_path), pipelines
    )

    assert client.pipeline_puts == [pipeline.name for pipeline in pipelines]
    assert waits == [5.0, 5.0, 5.0]
    assert client.pipeline_operations[:6] == [
        ("get", pipelines[0].name),
        ("get", pipelines[1].name),
        ("put", pipelines[0].name),
        ("put", pipelines[1].name),
        ("get", pipelines[0].name),
        ("get", pipelines[1].name),
    ]


def test_pipeline_mismatch_is_detected_before_any_put(tmp_path: Path) -> None:
    index_path = tmp_path / "index.json"
    natural_path = tmp_path / "natural.json"
    legal_path = tmp_path / "legal.json"
    _write_config(index_path)
    _write_pipeline(
        natural_path,
        profile="natural_language",
        name="synthetic-natural-staging-v1",
        bm25=0.4,
        vector=0.6,
    )
    _write_pipeline(
        legal_path,
        profile="legal",
        name="synthetic-legal-staging-v1",
        bm25=0.65,
        vector=0.35,
    )
    pipelines = (
        load_search_pipeline_definition(natural_path),
        load_search_pipeline_definition(legal_path),
    )
    client = FakeIndexClient()
    client.pipelines[pipelines[1].name] = {"phase_results_processors": [{"different": True}]}

    with pytest.raises(IndexConfigurationError, match="differs from config"):
        IndexManager(client).create_staging_resources(
            "synthetic-staging-v1", load_index_definition(index_path), pipelines
        )

    assert client.pipeline_puts == []
    assert client.created == []


def test_matching_existing_pipeline_is_reused_without_put(tmp_path: Path) -> None:
    index_path = tmp_path / "index.json"
    pipeline_path = tmp_path / "natural.json"
    _write_config(index_path)
    _write_pipeline(
        pipeline_path,
        profile="natural_language",
        name="synthetic-natural-staging-v1",
        bm25=0.4,
        vector=0.6,
    )
    pipeline = load_search_pipeline_definition(pipeline_path)
    client = FakeIndexClient()
    client.pipelines[pipeline.name] = pipeline.body

    IndexManager(client).create_staging_resources(
        "synthetic-staging-v1", load_index_definition(index_path), (pipeline,)
    )

    assert client.pipeline_puts == []
    assert client.created[0][0] == "synthetic-staging-v1"


def test_pipeline_inspection_reads_each_pipeline_once_without_mutation(tmp_path: Path) -> None:
    natural_path = tmp_path / "natural.json"
    legal_path = tmp_path / "legal.json"
    _write_pipeline(
        natural_path,
        profile="natural_language",
        name="synthetic-natural-staging-v1",
        bm25=0.4,
        vector=0.6,
    )
    _write_pipeline(
        legal_path,
        profile="legal",
        name="synthetic-legal-staging-v1",
        bm25=0.65,
        vector=0.35,
    )
    pipelines = (
        load_search_pipeline_definition(natural_path),
        load_search_pipeline_definition(legal_path),
    )
    client = FakeIndexClient()
    client.pipelines[pipelines[0].name] = pipelines[0].body
    client.pipelines[pipelines[1].name] = {"phase_results_processors": [{"different": True}]}

    inspections = IndexManager(client).inspect_search_pipelines(pipelines)

    assert [(item.name, item.status, item.config_match) for item in inspections] == [
        (pipelines[0].name, "VISIBLE", True),
        (pipelines[1].name, "VISIBLE", False),
    ]
    assert client.pipeline_gets == [pipeline.name for pipeline in pipelines]
    assert client.pipeline_puts == []
    assert client.deleted_pipelines == []
    assert client.created == []


def test_pipeline_inspection_reports_missing_without_a_configuration_match(tmp_path: Path) -> None:
    pipeline_path = tmp_path / "natural.json"
    _write_pipeline(
        pipeline_path,
        profile="natural_language",
        name="synthetic-natural-staging-v1",
        bm25=0.4,
        vector=0.6,
    )
    pipeline = load_search_pipeline_definition(pipeline_path)

    inspection = IndexManager(FakeIndexClient()).inspect_search_pipelines((pipeline,))[0]

    assert (inspection.status, inspection.config_match) == ("MISSING", None)


def test_default_visibility_window_is_sixty_seconds() -> None:
    assert RESOURCE_VISIBILITY_ATTEMPTS == 13


def test_alias_verification_requires_exactly_one_configured_target() -> None:
    client = FakeIndexClient()
    client.alias_target_names = ("synthetic-staging-v1",)

    IndexManager(client).verify_alias("synthetic-staging-v1", "synthetic-staging")

    client.alias_target_names = ("old-staging-v1", "synthetic-staging-v1")
    with pytest.raises(IndexConfigurationError, match="exactly"):
        IndexManager(client).verify_alias("synthetic-staging-v1", "synthetic-staging")
