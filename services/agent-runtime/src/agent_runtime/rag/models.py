from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0.0"
ID_REGEX = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
LANGUAGE_REGEX = r"^[a-z]{2,3}(?:-[A-Za-z]{2})?$"

QueryProfile = Literal["natural_language", "legal"]
RetrievalStatus = Literal["SUCCESS", "NO_DATA", "FAILED"]


class RagBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, strict=True)


class RetrievalRequestV1(RagBaseModel):
    """Wire model matching the staging retrieval request contract."""

    schema_version: Literal["1.0.0"]
    request_id: str = Field(min_length=2, max_length=128, pattern=ID_REGEX)
    query: str = Field(min_length=1, max_length=2000)
    query_profile: QueryProfile
    top_k: Literal[5]
    audience: str | None = Field(default=None, max_length=80)
    purpose: str | None = Field(default=None, max_length=120)
    language: str = Field(default="zh-TW", pattern=LANGUAGE_REGEX)

    @field_validator("query")
    @classmethod
    def query_must_contain_non_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must contain non-whitespace text")
        return value


class RetrievalResultV1(RagBaseModel):
    """A chunk plus the citation fields the agent must preserve in its answer."""

    chunk_id: str = Field(min_length=1, max_length=256)
    text: str = Field(min_length=1, max_length=50000)
    score: float = Field(allow_inf_nan=False)
    document_name: str = Field(min_length=1, max_length=512)
    section: str = Field(min_length=1, max_length=512)
    # Null for sources that have no pagination, such as an official web page,
    # where source_locator carries the position instead. Both or neither: a
    # half-populated range is a data defect, not a citable location.
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    source_url: str = Field(min_length=1, max_length=2048)

    @field_validator("source_url")
    @classmethod
    def source_url_must_be_absolute(cls, value: str) -> str:
        if not value.startswith(("https://", "http://")):
            raise ValueError("source_url must be an absolute HTTP(S) URI")
        return value

    @model_validator(mode="after")
    def page_range_must_be_ordered(self) -> RetrievalResultV1:
        if (self.page_start is None) != (self.page_end is None):
            raise ValueError("page_start and page_end must both be set or both be null")
        if self.page_start is not None and self.page_end is not None:
            if self.page_end < self.page_start:
                raise ValueError("page_end must be greater than or equal to page_start")
        return self


class RetrievalResponseV1(RagBaseModel):
    """Wire model matching the staging retrieval response contract."""

    schema_version: Literal["1.0.0"]
    request_id: str = Field(min_length=2, max_length=128, pattern=ID_REGEX)
    status: RetrievalStatus
    fallback_message: str | None = Field(max_length=1000)
    results: list[RetrievalResultV1] = Field(max_length=5)

    @model_validator(mode="after")
    def status_and_results_must_be_consistent(self) -> RetrievalResponseV1:
        if self.status == "SUCCESS":
            if self.fallback_message is not None:
                raise ValueError("successful retrieval cannot include a fallback message")
            if not 3 <= len(self.results) <= 5:
                raise ValueError("successful retrieval must provide three to five chunks")
        else:
            if not self.fallback_message or not self.fallback_message.strip():
                raise ValueError("non-success retrieval must include an explicit fallback message")
            if self.results:
                raise ValueError("fallback retrieval must not expose partial results to the agent")
        return self


class QueryEmbeddingSettings(RagBaseModel):
    """Bedrock query settings supplied by configuration/environment wiring."""

    model_id: str = Field(min_length=1)
    region: str = Field(min_length=1)
    dimension: Literal[1024]


class HybridProfileSettings(RagBaseModel):
    """Runtime subset of a configured OpenSearch search pipeline."""

    profile: QueryProfile
    search_pipeline: str = Field(min_length=1)
    bm25_weight: float = Field(ge=0.0, le=1.0)
    vector_weight: float = Field(ge=0.0, le=1.0)
    vector_min_score: float = Field(gt=0.0, le=1.0)
    top_k: Literal[5]
    agent_chunk_min: Literal[3]
    agent_chunk_max: Literal[5]

    @model_validator(mode="after")
    def weights_must_be_normalized(self) -> HybridProfileSettings:
        if abs((self.bm25_weight + self.vector_weight) - 1.0) > 1e-9:
            raise ValueError("hybrid weights must sum to 1")
        return self

    @classmethod
    def from_config(cls, values: Mapping[str, object]) -> HybridProfileSettings:
        """Select the runtime-safe subset from the full pipeline configuration file."""

        return cls.model_validate(
            {
                "profile": values.get("profile"),
                "search_pipeline": values.get("search_pipeline"),
                "bm25_weight": values.get("bm25_weight"),
                "vector_weight": values.get("vector_weight"),
                "vector_min_score": values.get("vector_min_score"),
                "top_k": values.get("top_k"),
                "agent_chunk_min": values.get("agent_chunk_min"),
                "agent_chunk_max": values.get("agent_chunk_max"),
            }
        )


class HybridSearchSettings(RagBaseModel):
    """Both approved search profiles and their configured index alias."""

    index_alias: str = Field(min_length=1)
    natural_language: HybridProfileSettings
    legal: HybridProfileSettings

    @model_validator(mode="after")
    def profile_slots_must_match(self) -> HybridSearchSettings:
        if self.natural_language.profile != "natural_language":
            raise ValueError("natural_language slot contains the wrong profile")
        if self.legal.profile != "legal":
            raise ValueError("legal slot contains the wrong profile")
        return self

    def for_profile(self, profile: QueryProfile) -> HybridProfileSettings:
        if profile == "legal":
            return self.legal
        return self.natural_language


class OpenSearchConnectionSettings(RagBaseModel):
    """AWS OpenSearch connection values resolved from configuration/environment."""

    host: str = Field(min_length=1)
    region: str = Field(min_length=1)
    index_name: str = Field(min_length=1)
    index_alias: str = Field(min_length=1)
    mode: Literal["staging"]

    @field_validator("index_name", "index_alias")
    @classmethod
    def index_targets_must_be_explicitly_staging(cls, value: str) -> str:
        normalized = value.casefold()
        if "staging" not in normalized or "production" in normalized or "prod" in normalized:
            raise ValueError("OpenSearch index and alias must be explicitly staging")
        return value


class RagRuntimeSettings(RagBaseModel):
    """Complete online retrieval settings with no provider values baked into code."""

    embedding: QueryEmbeddingSettings
    opensearch: OpenSearchConnectionSettings
    hybrid: HybridSearchSettings

    @classmethod
    def from_config_files(
        cls,
        *,
        embedding_config_path: str | Path,
        index_config_path: str | Path,
        natural_profile_path: str | Path,
        legal_profile_path: str | Path,
        environ: Mapping[str, str] | None = None,
    ) -> RagRuntimeSettings:
        """Load explicit paths and let named environment values override file values."""

        env = os.environ if environ is None else environ
        embedding_document = _read_yaml_mapping(embedding_config_path)
        index_document = _read_json_mapping(index_config_path)
        natural_document = _read_json_mapping(natural_profile_path)
        legal_document = _read_json_mapping(legal_profile_path)

        embedding_values = _required_mapping(embedding_document, "embedding")
        index_values = _required_mapping(index_document, "index")
        model_id = _resolve_config_value(embedding_values, "model_id", "model_id_env", env)
        region = _resolve_config_value(embedding_values, "region", "region_env", env)
        dimension = _resolve_config_value(
            embedding_values,
            "dimension",
            "dimension_env",
            env,
        )
        index_name = _resolve_config_value(index_values, "name", "name_env", env)
        index_alias = _resolve_config_value(index_values, "alias", "alias_env", env)
        host = _required_env(env, "OPENSEARCH_HOST")
        mode = env.get("RAG_MODE") or index_document.get("mode")

        embedding = QueryEmbeddingSettings(
            model_id=_as_nonempty_str(model_id, "embedding model ID"),
            region=_as_nonempty_str(region, "AWS region"),
            dimension=_as_int(dimension, "embedding dimension"),
        )
        opensearch = OpenSearchConnectionSettings(
            host=host,
            region=embedding.region,
            index_name=_as_nonempty_str(index_name, "OpenSearch index name"),
            index_alias=_as_nonempty_str(index_alias, "OpenSearch index alias"),
            mode=mode,
        )
        natural = HybridProfileSettings.from_config(natural_document)
        legal = HybridProfileSettings.from_config(legal_document)
        return cls(
            embedding=embedding,
            opensearch=opensearch,
            hybrid=HybridSearchSettings(
                index_alias=opensearch.index_alias,
                natural_language=natural,
                legal=legal,
            ),
        )


class HybridSearchPlan(RagBaseModel):
    """Parameterised OpenSearch request; never accepts caller-provided DSL."""

    index_alias: str = Field(min_length=1)
    search_pipeline: str = Field(min_length=1)
    profile: QueryProfile
    bm25_weight: float
    vector_weight: float
    # Applied by Retriever to the pipeline-normalized hit score, because the
    # collection's knn clause accepts only `k` and cannot carry a floor itself.
    min_score: float = Field(gt=0.0, le=1.0)
    body: dict[str, object]


def _read_yaml_mapping(path: str | Path) -> Mapping[str, object]:
    try:
        document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot load RAG YAML configuration: {path}") from exc
    if not isinstance(document, Mapping):
        raise ValueError(f"RAG YAML configuration must contain an object: {path}")
    return document


def _read_json_mapping(path: str | Path) -> Mapping[str, object]:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load RAG JSON configuration: {path}") from exc
    if not isinstance(document, Mapping):
        raise ValueError(f"RAG JSON configuration must contain an object: {path}")
    return document


def _required_mapping(document: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = document.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"RAG configuration is missing object: {key}")
    return value


def _resolve_config_value(
    values: Mapping[str, object],
    value_key: str,
    env_key_key: str,
    environ: Mapping[str, str],
) -> object:
    env_key = values.get(env_key_key)
    if isinstance(env_key, str):
        env_value = environ.get(env_key)
        if env_value is not None and env_value.strip():
            return env_value.strip()
    value = values.get(value_key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"RAG configuration value is missing: {value_key}")
    return value


def _required_env(environ: Mapping[str, str], key: str) -> str:
    value = environ.get(key)
    if value is None or not value.strip():
        raise ValueError(f"required RAG environment value is missing: {key}")
    return value.strip()


def _as_int(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer") from exc


def _as_nonempty_str(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()
