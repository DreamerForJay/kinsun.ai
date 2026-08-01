"""Staging index lifecycle with dimension and production guards."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import sleep
from typing import Any, Protocol

from rag_ingestion.settings import REQUIRED_EMBEDDING_DIMENSION

REQUIRED_VECTOR_TYPE = "knn_vector"
REQUIRED_VECTOR_SPACE_TYPE = "cosinesimil"
REQUIRED_VECTOR_METHOD_NAME = "hnsw"
# OpenSearch Serverless resource writes can be acknowledged well before the
# corresponding read API exposes them. Poll at 0, 5, ..., 60 seconds.
RESOURCE_VISIBILITY_ATTEMPTS = 13
RESOURCE_VISIBILITY_DELAY_SECONDS = 5.0


class IndexConfigurationError(ValueError):
    """Raised when an index definition is unsafe or inconsistent."""


class IndexClient(Protocol):
    def index_exists(self, index_name: str) -> bool: ...

    def create_index(self, index_name: str, body: dict[str, Any]) -> None: ...

    def delete_index(self, index_name: str) -> None: ...

    def get_mapping(self, index_name: str) -> dict[str, Any]: ...

    def set_alias(self, index_name: str, alias_name: str) -> None: ...

    def alias_targets(self, alias_name: str) -> tuple[str, ...]: ...

    def get_search_pipeline(self, pipeline_name: str) -> dict[str, Any] | None: ...

    def put_search_pipeline(self, pipeline_name: str, body: dict[str, Any]) -> None: ...

    def delete_search_pipeline(self, pipeline_name: str) -> None: ...


@dataclass(frozen=True, slots=True)
class IndexDefinition:
    mode: str
    configured_name: str
    configured_alias: str
    body: dict[str, Any]
    vector_dimension: int


@dataclass(frozen=True, slots=True)
class SearchPipelineDefinition:
    profile: str
    name: str
    bm25_weight: float
    vector_weight: float
    body: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SearchPipelineInspection:
    """Minimal, non-sensitive result from one search-pipeline read."""

    name: str
    status: str
    config_match: bool | None


class IndexManager:
    def __init__(
        self,
        client: IndexClient,
        *,
        sleeper: Callable[[float], None] = sleep,
        visibility_attempts: int = RESOURCE_VISIBILITY_ATTEMPTS,
        visibility_delay_seconds: float = RESOURCE_VISIBILITY_DELAY_SECONDS,
    ) -> None:
        if visibility_attempts < 1:
            raise ValueError("visibility_attempts must be at least one")
        if visibility_delay_seconds < 0:
            raise ValueError("visibility_delay_seconds must not be negative")
        self._client = client
        self._sleeper = sleeper
        self._visibility_attempts = visibility_attempts
        self._visibility_delay_seconds = visibility_delay_seconds

    def create_staging_index(self, index_name: str, definition: IndexDefinition) -> None:
        self._validate_staging_index_request(index_name, definition)
        if self._client.index_exists(index_name):
            raise IndexConfigurationError("staging index already exists; refusing to overwrite")
        self._client.create_index(index_name, definition.body)
        try:
            self.verify_mapping_dimension(index_name, REQUIRED_EMBEDDING_DIMENSION)
        except Exception:
            try:
                self._client.delete_index(index_name)
            except Exception as rollback_exc:
                raise IndexConfigurationError(
                    "index mapping verification failed and staging rollback was incomplete"
                ) from rollback_exc
            raise

    def _validate_staging_index_request(self, index_name: str, definition: IndexDefinition) -> None:
        _require_staging_name(index_name)
        if definition.mode.casefold() != "staging":
            raise IndexConfigurationError("index definition mode must be staging")
        if definition.configured_name != index_name:
            raise IndexConfigurationError("requested index does not match configured staging index")
        if definition.vector_dimension != REQUIRED_EMBEDDING_DIMENSION:
            raise IndexConfigurationError(
                f"index vector dimension must be {REQUIRED_EMBEDDING_DIMENSION}"
            )

    def create_staging_resources(
        self,
        index_name: str,
        definition: IndexDefinition,
        pipelines: tuple[SearchPipelineDefinition, ...],
    ) -> None:
        """Reconcile pipelines, then create a verified staging index.

        Pipeline writes acknowledged but not yet visible are deliberately retained.
        A later run can safely reuse them after an exact configuration match.
        """

        self._validate_staging_index_request(index_name, definition)
        if self._client.index_exists(index_name):
            raise IndexConfigurationError("staging index already exists; refusing to overwrite")
        self._validate_search_pipeline_names(pipelines)

        missing: list[SearchPipelineDefinition] = []
        for pipeline in pipelines:
            existing = self._client.get_search_pipeline(pipeline.name)
            if existing is None:
                missing.append(pipeline)
            elif not _same_pipeline(existing, pipeline.body):
                raise IndexConfigurationError(
                    f"existing search pipeline differs from config: {pipeline.name}"
                )

        acknowledged: list[str] = []
        try:
            for pipeline in missing:
                self._client.put_search_pipeline(pipeline.name, pipeline.body)
                acknowledged.append(pipeline.name)
            self.verify_search_pipelines(pipelines)
            self.create_staging_index(index_name, definition)
        except IndexConfigurationError as exc:
            if acknowledged:
                raise IndexConfigurationError(
                    f"{exc}; acknowledged search pipelines retained for safe reconciliation: "
                    + ", ".join(acknowledged)
                ) from exc
            raise

    def verify_mapping_dimension(self, index_name: str, expected_dimension: int) -> None:
        for attempt in range(self._visibility_attempts):
            try:
                mapping = self._client.get_mapping(index_name)
                dimension = _mapping_dimension(mapping, index_name)
            except Exception as exc:
                if not _mapping_not_yet_visible(exc):
                    raise
                if attempt == self._visibility_attempts - 1:
                    raise IndexConfigurationError(
                        f"OpenSearch mapping verification timed out: {index_name}"
                    ) from exc
                self._wait_for_resource_visibility()
                continue
            if dimension != expected_dimension:
                raise IndexConfigurationError(
                    f"OpenSearch mapping dimension is {dimension}, expected {expected_dimension}"
                )
            return

    def activate_alias(self, index_name: str, alias_name: str) -> None:
        _require_staging_name(index_name)
        _require_staging_name(alias_name)
        self._client.set_alias(index_name, alias_name)

    def verify_alias(self, index_name: str, alias_name: str) -> None:
        _require_staging_name(index_name)
        _require_staging_name(alias_name)
        targets = self._client.alias_targets(alias_name)
        if targets != (index_name,):
            raise IndexConfigurationError(
                "configured staging alias must point to exactly the configured staging index"
            )

    def verify_search_pipeline(self, pipeline: SearchPipelineDefinition) -> None:
        self.verify_search_pipelines((pipeline,))

    def inspect_search_pipelines(
        self, pipelines: tuple[SearchPipelineDefinition, ...]
    ) -> tuple[SearchPipelineInspection, ...]:
        """Read each configured pipeline once without changing OpenSearch state."""

        self._validate_search_pipeline_names(pipelines)
        inspections: list[SearchPipelineInspection] = []
        for pipeline in pipelines:
            actual = self._client.get_search_pipeline(pipeline.name)
            if actual is None:
                inspections.append(
                    SearchPipelineInspection(
                        name=pipeline.name,
                        status="MISSING",
                        config_match=None,
                    )
                )
                continue
            inspections.append(
                SearchPipelineInspection(
                    name=pipeline.name,
                    status="VISIBLE",
                    config_match=_same_pipeline(actual, pipeline.body),
                )
            )
        return tuple(inspections)

    def verify_search_pipelines(self, pipelines: tuple[SearchPipelineDefinition, ...]) -> None:
        self._validate_search_pipeline_names(pipelines)
        pending = {pipeline.name: pipeline for pipeline in pipelines}
        for attempt in range(self._visibility_attempts):
            for pipeline_name, pipeline in tuple(pending.items()):
                actual = self._client.get_search_pipeline(pipeline_name)
                if actual is None:
                    continue
                if not _same_pipeline(actual, pipeline.body):
                    raise IndexConfigurationError(
                        f"search pipeline verification failed: {pipeline_name}"
                    )
                del pending[pipeline_name]
            if not pending:
                return
            if attempt == self._visibility_attempts - 1:
                raise IndexConfigurationError(
                    "search pipeline verification timed out: " + ", ".join(pending)
                )
            self._wait_for_resource_visibility()

    @staticmethod
    def _validate_search_pipeline_names(
        pipelines: tuple[SearchPipelineDefinition, ...],
    ) -> None:
        for pipeline in pipelines:
            _require_staging_name(pipeline.name)
        if len({pipeline.name for pipeline in pipelines}) != len(pipelines):
            raise IndexConfigurationError("search pipeline names must be unique")

    def _wait_for_resource_visibility(self) -> None:
        self._sleeper(self._visibility_delay_seconds)


def load_index_definition(path: Path) -> IndexDefinition:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IndexConfigurationError(
            f"cannot read index configuration: {type(exc).__name__}"
        ) from exc
    if not isinstance(raw, dict):
        raise IndexConfigurationError("index configuration root must be an object")
    index = raw.get("index")
    settings = raw.get("settings")
    mappings = raw.get("mappings")
    if (
        not isinstance(index, dict)
        or not isinstance(settings, dict)
        or not isinstance(mappings, dict)
    ):
        raise IndexConfigurationError("index configuration is missing index/settings/mappings")
    name = index.get("name")
    alias = index.get("alias")
    mode = raw.get("mode")
    if not all(isinstance(value, str) and value.strip() for value in (name, alias, mode)):
        raise IndexConfigurationError("index name, alias, and mode are required")
    _require_staging_name(name)
    _require_staging_name(alias)
    try:
        embedding_mapping = mappings["properties"]["embedding"]
    except (KeyError, TypeError) as exc:
        raise IndexConfigurationError("embedding mapping is required") from exc
    if not isinstance(embedding_mapping, dict):
        raise IndexConfigurationError("embedding mapping must be an object")
    vector_type = embedding_mapping.get("type")
    dimension = embedding_mapping.get("dimension")
    space_type = embedding_mapping.get("space_type")
    method = embedding_mapping.get("method")
    if vector_type != REQUIRED_VECTOR_TYPE:
        raise IndexConfigurationError(f"embedding mapping type must be {REQUIRED_VECTOR_TYPE}")
    if isinstance(dimension, bool) or not isinstance(dimension, int):
        raise IndexConfigurationError("embedding mapping dimension must be an integer")
    if dimension != REQUIRED_EMBEDDING_DIMENSION:
        raise IndexConfigurationError(
            "embedding mapping dimension must be " f"{REQUIRED_EMBEDDING_DIMENSION}"
        )
    if space_type != REQUIRED_VECTOR_SPACE_TYPE:
        raise IndexConfigurationError(
            "embedding mapping space_type must be " f"{REQUIRED_VECTOR_SPACE_TYPE}"
        )
    if not isinstance(method, dict):
        raise IndexConfigurationError("embedding mapping method must be an object")
    if "engine" in method:
        raise IndexConfigurationError(
            "OpenSearch Serverless NextGen vector mappings must not set method.engine"
        )
    if set(method) != {"name"} or method.get("name") != REQUIRED_VECTOR_METHOD_NAME:
        raise IndexConfigurationError(
            "embedding mapping method must contain only name=" f"{REQUIRED_VECTOR_METHOD_NAME}"
        )
    return IndexDefinition(
        mode=mode,
        configured_name=name,
        configured_alias=alias,
        body={"settings": settings, "mappings": mappings},
        vector_dimension=dimension,
    )


def load_search_pipeline_definition(path: Path) -> SearchPipelineDefinition:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IndexConfigurationError(
            f"cannot read search-pipeline configuration: {type(exc).__name__}"
        ) from exc
    if not isinstance(raw, dict):
        raise IndexConfigurationError("search-pipeline configuration root must be an object")
    profile = raw.get("profile")
    name = raw.get("search_pipeline")
    bm25_weight = raw.get("bm25_weight")
    vector_weight = raw.get("vector_weight")
    body = raw.get("pipeline")
    if not isinstance(profile, str) or profile not in {"natural_language", "legal"}:
        raise IndexConfigurationError("search-pipeline profile is invalid")
    if not isinstance(name, str) or not name.strip():
        raise IndexConfigurationError("search-pipeline name is required")
    _require_staging_name(name)
    if (
        isinstance(bm25_weight, bool)
        or not isinstance(bm25_weight, int | float)
        or isinstance(vector_weight, bool)
        or not isinstance(vector_weight, int | float)
    ):
        raise IndexConfigurationError("search-pipeline weights must be numeric")
    bm25_weight = float(bm25_weight)
    vector_weight = float(vector_weight)
    if not 0 <= bm25_weight <= 1 or not 0 <= vector_weight <= 1:
        raise IndexConfigurationError("search-pipeline weights must be between zero and one")
    if abs((bm25_weight + vector_weight) - 1.0) > 1e-9:
        raise IndexConfigurationError("search-pipeline weights must sum to one")
    if not isinstance(body, dict):
        raise IndexConfigurationError("search-pipeline body must be an object")
    configured_weights = _pipeline_weights(body)
    if configured_weights != (bm25_weight, vector_weight):
        raise IndexConfigurationError(
            "declared search-pipeline weights do not match processor weights"
        )
    return SearchPipelineDefinition(
        profile=profile,
        name=name,
        bm25_weight=bm25_weight,
        vector_weight=vector_weight,
        body=body,
    )


def _mapping_dimension(mapping: dict[str, Any], index_name: str) -> int:
    root = mapping.get(index_name)
    if root is None and len(mapping) == 1:
        root = next(iter(mapping.values()))
    try:
        dimension = root["mappings"]["properties"]["embedding"]["dimension"]
    except (KeyError, TypeError) as exc:
        raise IndexConfigurationError("OpenSearch mapping has no embedding dimension") from exc
    if isinstance(dimension, bool) or not isinstance(dimension, int):
        raise IndexConfigurationError("OpenSearch embedding dimension is invalid")
    return dimension


def _mapping_not_yet_visible(exc: Exception) -> bool:
    """Return whether a read failed solely because the new index is not visible."""

    return getattr(exc, "status_code", None) == 404 or (
        isinstance(exc, IndexConfigurationError)
        and str(exc) == "OpenSearch mapping has no embedding dimension"
    )


def _require_staging_name(value: str) -> None:
    normalized = value.casefold()
    if "staging" not in normalized or "production" in normalized or "prod" in normalized:
        raise IndexConfigurationError("only explicitly named staging indexes/aliases are allowed")


def _pipeline_weights(body: dict[str, Any]) -> tuple[float, float]:
    try:
        processors = body["phase_results_processors"]
        weights = processors[0]["normalization-processor"]["combination"]["parameters"]["weights"]
    except (KeyError, IndexError, TypeError) as exc:
        raise IndexConfigurationError("search-pipeline normalization weights are missing") from exc
    if (
        not isinstance(weights, list)
        or len(weights) != 2
        or any(isinstance(value, bool) or not isinstance(value, int | float) for value in weights)
    ):
        raise IndexConfigurationError("search-pipeline processor weights are invalid")
    return float(weights[0]), float(weights[1])


def _same_pipeline(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    return actual.get("phase_results_processors") == expected.get("phase_results_processors")
