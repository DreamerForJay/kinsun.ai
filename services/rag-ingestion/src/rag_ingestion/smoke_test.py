"""End-to-end Agent Runtime retrieval smoke test over the public HTTP contract."""

from __future__ import annotations

import json
import math
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,127}$")
LANGUAGE_PATTERN = re.compile(r"^[a-z]{2,3}(?:-[A-Za-z]{2})?$")
MAX_RESPONSE_BYTES = 1_048_576
RETRIEVAL_ENDPOINT_PATH = "/api/v1/rag/retrievals"


class SmokeTestError(RuntimeError):
    """Raised unless both retrieval contract scenarios pass completely."""


@dataclass(frozen=True, slots=True)
class SmokeTestDefinition:
    endpoint_path: str
    timeout_seconds: float
    positive_request: dict[str, Any]
    no_data_request: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AgentRuntimeSmokeReport:
    endpoint_path: str
    positive_status: str
    positive_result_count: int
    no_data_status: str
    no_data_result_count: int
    no_data_fallback_present: bool


def load_smoke_test_definition(path: Path) -> SmokeTestDefinition:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SmokeTestError(f"cannot read smoke-test configuration: {type(exc).__name__}") from exc
    expected_keys = {
        "schema_version",
        "mode",
        "endpoint_path",
        "timeout_seconds",
        "positive_request",
        "no_data_request",
    }
    if not isinstance(raw, dict) or set(raw) != expected_keys:
        raise SmokeTestError("smoke-test configuration shape is invalid")
    if raw.get("schema_version") != "1.0.0" or raw.get("mode") != "staging":
        raise SmokeTestError("smoke-test configuration must be staging schema 1.0.0")
    endpoint_path = raw.get("endpoint_path")
    if (
        not isinstance(endpoint_path, str)
        or not _safe_endpoint_path(endpoint_path)
        or endpoint_path != RETRIEVAL_ENDPOINT_PATH
    ):
        raise SmokeTestError("smoke-test endpoint path is invalid")
    timeout = raw.get("timeout_seconds")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, int | float)
        or not 1 <= float(timeout) <= 60
    ):
        raise SmokeTestError("smoke-test timeout must be between 1 and 60 seconds")
    positive = _validate_request(raw.get("positive_request"), "positive")
    no_data = _validate_request(raw.get("no_data_request"), "no-data")
    if positive["request_id"] == no_data["request_id"]:
        raise SmokeTestError("smoke-test request IDs must be distinct")
    if positive["query"] == no_data["query"]:
        raise SmokeTestError("positive and no-data smoke queries must be distinct")
    return SmokeTestDefinition(
        endpoint_path=endpoint_path,
        timeout_seconds=float(timeout),
        positive_request=positive,
        no_data_request=no_data,
    )


def run_agent_runtime_smoke(
    *,
    base_url: str,
    definition: SmokeTestDefinition,
    opener: Callable[..., Any] | None = None,
) -> AgentRuntimeSmokeReport:
    endpoint = _build_endpoint(base_url, definition.endpoint_path)
    positive = _post_json(
        endpoint,
        definition.positive_request,
        timeout=definition.timeout_seconds,
        opener=opener,
    )
    positive_count = _validate_positive_envelope(
        positive, definition.positive_request["request_id"]
    )
    no_data = _post_json(
        endpoint,
        definition.no_data_request,
        timeout=definition.timeout_seconds,
        opener=opener,
    )
    _validate_no_data_envelope(
        no_data,
        definition.no_data_request["request_id"],
        definition.no_data_request["query"],
    )
    return AgentRuntimeSmokeReport(
        endpoint_path=definition.endpoint_path,
        positive_status="SUCCESS",
        positive_result_count=positive_count,
        no_data_status="NO_DATA",
        no_data_result_count=0,
        no_data_fallback_present=True,
    )


def _validate_request(value: Any, label: str) -> dict[str, Any]:
    required = {"schema_version", "request_id", "query", "query_profile", "top_k", "language"}
    optional = {"audience", "purpose"}
    if (
        not isinstance(value, dict)
        or not required.issubset(value)
        or not set(value) <= required | optional
    ):
        raise SmokeTestError(f"{label} smoke request shape is invalid")
    if value.get("schema_version") != "1.0.0":
        raise SmokeTestError(f"{label} smoke request schema version is invalid")
    request_id = value.get("request_id")
    if not isinstance(request_id, str) or not REQUEST_ID_PATTERN.fullmatch(request_id):
        raise SmokeTestError(f"{label} smoke request_id is invalid")
    query = value.get("query")
    if not isinstance(query, str) or not query.strip() or len(query) > 2000:
        raise SmokeTestError(f"{label} smoke query is invalid")
    if value.get("query_profile") not in {"natural_language", "legal"}:
        raise SmokeTestError(f"{label} smoke query profile is invalid")
    top_k = value.get("top_k")
    if isinstance(top_k, bool) or top_k != 5:
        raise SmokeTestError(f"{label} smoke top_k must be 5")
    language = value.get("language")
    if not isinstance(language, str) or not LANGUAGE_PATTERN.fullmatch(language):
        raise SmokeTestError(f"{label} smoke language is invalid")
    for name, maximum in (("audience", 80), ("purpose", 120)):
        field = value.get(name)
        if field is not None and (
            not isinstance(field, str) or not field.strip() or len(field) > maximum
        ):
            raise SmokeTestError(f"{label} smoke {name} is invalid")
    return dict(value)


def _safe_endpoint_path(value: str) -> bool:
    parsed = urlsplit(value)
    return (
        value.startswith("/")
        and parsed.scheme == ""
        and parsed.netloc == ""
        and parsed.query == ""
        and parsed.fragment == ""
        and ".." not in parsed.path.split("/")
    )


def _build_endpoint(base_url: str, endpoint_path: str) -> str:
    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise SmokeTestError("AGENT_RUNTIME_BASE_URL must be an HTTP(S) origin without credentials")
    return base_url.rstrip("/") + endpoint_path


def _post_json(
    endpoint: str,
    payload: dict[str, Any],
    *,
    timeout: float,
    opener: Callable[..., Any] | None,
) -> dict[str, Any]:
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    open_request = opener or urllib.request.urlopen
    try:
        with open_request(request, timeout=timeout) as response:
            status = response.getcode()
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise SmokeTestError(f"Agent Runtime smoke request returned HTTP {exc.code}") from exc
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        raise SmokeTestError(f"Agent Runtime smoke request failed: {type(exc).__name__}") from exc
    if status != 200:
        raise SmokeTestError(f"Agent Runtime smoke request returned HTTP {status}")
    if not isinstance(body, bytes) or len(body) > MAX_RESPONSE_BYTES:
        raise SmokeTestError("Agent Runtime smoke response is invalid or too large")
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SmokeTestError("Agent Runtime smoke response is not UTF-8 JSON") from exc
    if not isinstance(parsed, dict):
        raise SmokeTestError("Agent Runtime smoke response root must be an object")
    return parsed


def _validate_positive_envelope(envelope: dict[str, Any], request_id: str) -> int:
    data = _validate_envelope(envelope, request_id)
    if data.get("status") != "SUCCESS":
        raise SmokeTestError("positive retrieval smoke did not return SUCCESS")
    if data.get("fallback_message") is not None:
        raise SmokeTestError("positive retrieval smoke returned a fallback message")
    results = data.get("results")
    if not isinstance(results, list) or not 3 <= len(results) <= 5:
        raise SmokeTestError("positive retrieval smoke must return three to five chunks")
    chunk_ids: set[str] = set()
    for result in results:
        chunk_id = _validate_cited_result(result)
        if chunk_id in chunk_ids:
            raise SmokeTestError("positive retrieval smoke returned duplicate chunk IDs")
        chunk_ids.add(chunk_id)
    return len(results)


def _validate_no_data_envelope(envelope: dict[str, Any], request_id: str, query: str) -> None:
    data = _validate_envelope(envelope, request_id)
    if data.get("status") != "NO_DATA":
        raise SmokeTestError("no-data retrieval smoke did not return NO_DATA")
    if data.get("results") != []:
        raise SmokeTestError("no-data retrieval smoke returned result chunks")
    fallback = data.get("fallback_message")
    if not isinstance(fallback, str) or not fallback.strip() or len(fallback) > 1000:
        raise SmokeTestError("no-data retrieval smoke has no explicit fallback")
    if query.casefold() in fallback.casefold():
        raise SmokeTestError("no-data retrieval fallback echoed the query")


def _validate_envelope(envelope: dict[str, Any], request_id: str) -> dict[str, Any]:
    if set(envelope) != {"data", "meta"}:
        raise SmokeTestError("Agent Runtime response is not a SuccessEnvelope")
    meta = envelope.get("meta")
    if not isinstance(meta, dict) or set(meta) != {
        "correlation_id",
        "timestamp",
        "schema_version",
    }:
        raise SmokeTestError("Agent Runtime response meta shape is invalid")
    if meta.get("schema_version") != "1.0":
        raise SmokeTestError("Agent Runtime response meta schema version is invalid")
    if not isinstance(meta.get("correlation_id"), str) or not meta["correlation_id"].strip():
        raise SmokeTestError("Agent Runtime response correlation ID is missing")
    timestamp = meta.get("timestamp")
    if not isinstance(timestamp, str):
        raise SmokeTestError("Agent Runtime response timestamp is invalid")
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SmokeTestError("Agent Runtime response timestamp is invalid") from exc
    data = envelope.get("data")
    if not isinstance(data, dict) or set(data) != {
        "schema_version",
        "request_id",
        "status",
        "fallback_message",
        "results",
    }:
        raise SmokeTestError("retrieval response data shape is invalid")
    if data.get("schema_version") != "1.0.0" or data.get("request_id") != request_id:
        raise SmokeTestError("retrieval response identity does not match request")
    return data


def _validate_cited_result(value: Any) -> str:
    expected_keys = {
        "chunk_id",
        "text",
        "score",
        "document_name",
        "section",
        "page_start",
        "page_end",
        "source_url",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise SmokeTestError("retrieval result shape is invalid")
    maximum_lengths = {
        "chunk_id": 256,
        "text": 50000,
        "document_name": 512,
        "section": 512,
    }
    for name, maximum in maximum_lengths.items():
        field = value.get(name)
        if not isinstance(field, str) or not field.strip() or len(field) > maximum:
            raise SmokeTestError(f"retrieval result citation field is missing: {name}")
    score = value.get("score")
    if isinstance(score, bool) or not isinstance(score, int | float) or not math.isfinite(score):
        raise SmokeTestError("retrieval result score is invalid")
    page_start = value.get("page_start")
    page_end = value.get("page_end")
    if (
        isinstance(page_start, bool)
        or not isinstance(page_start, int)
        or page_start < 1
        or isinstance(page_end, bool)
        or not isinstance(page_end, int)
        or page_end < page_start
    ):
        raise SmokeTestError("retrieval result page citation is invalid")
    source_url = value.get("source_url")
    parsed_url = urlsplit(source_url) if isinstance(source_url, str) else None
    if (
        parsed_url is None
        or len(source_url) > 2048
        or parsed_url.scheme not in {"http", "https"}
        or not parsed_url.netloc
    ):
        raise SmokeTestError("retrieval result source URL is invalid")
    return value["chunk_id"]
