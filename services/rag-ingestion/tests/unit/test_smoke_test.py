from __future__ import annotations

import json
import urllib.error
from pathlib import Path
from typing import Any

import pytest

from rag_ingestion.smoke_test import (
    SmokeTestDefinition,
    SmokeTestError,
    load_smoke_test_definition,
    run_agent_runtime_smoke,
)


class FakeResponse:
    def __init__(self, payload: dict[str, Any], *, status: int = 200) -> None:
        self.payload = json.dumps(payload).encode("utf-8")
        self.status = status

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def getcode(self) -> int:
        return self.status

    def read(self, size: int = -1) -> bytes:
        return self.payload if size < 0 else self.payload[:size]


class RecordingOpener:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, float, dict[str, Any]]] = []

    def __call__(self, request: Any, *, timeout: float) -> FakeResponse:
        self.requests.append(
            (
                request.get_full_url(),
                timeout,
                json.loads(request.data.decode("utf-8")),
            )
        )
        return self.responses.pop(0)


def _definition() -> SmokeTestDefinition:
    return SmokeTestDefinition(
        endpoint_path="/api/v1/rag/retrievals",
        timeout_seconds=5.0,
        positive_request={
            "schema_version": "1.0.0",
            "request_id": "rag-smoke-positive",
            "query": "positive configured query",
            "query_profile": "natural_language",
            "top_k": 5,
            "language": "zh-TW",
        },
        no_data_request={
            "schema_version": "1.0.0",
            "request_id": "rag-smoke-no-data",
            "query": "negative configured query",
            "query_profile": "natural_language",
            "top_k": 5,
            "purpose": "no_match_sentinel",
            "language": "zh-TW",
        },
    )


def _envelope(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "data": data,
        "meta": {
            "correlation_id": "corr-smoke-001",
            "timestamp": "2026-08-01T00:00:00Z",
            "schema_version": "1.0",
        },
    }


def _positive_data() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "request_id": "rag-smoke-positive",
        "status": "SUCCESS",
        "fallback_message": None,
        "results": [
            {
                "chunk_id": f"chunk-{index}",
                "text": f"approved chunk text {index}",
                "score": 1.0 - index / 10,
                "document_name": "Approved Guide",
                "section": f"Section {index}",
                "page_start": index,
                "page_end": index,
                "source_url": f"https://example.invalid/source#{index}",
            }
            for index in range(1, 4)
        ],
    }


def _no_data() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "request_id": "rag-smoke-no-data",
        "status": "NO_DATA",
        "fallback_message": "No approved source was found.",
        "results": [],
    }


def test_checked_in_smoke_config_has_distinct_positive_and_no_data_requests() -> None:
    repository_root = Path(__file__).resolve().parents[4]

    definition = load_smoke_test_definition(repository_root / "config" / "rag" / "smoke-test.yaml")

    assert definition.positive_request["query"] != definition.no_data_request["query"]
    assert definition.no_data_request["purpose"] == "rag_smoke_no_match_purpose_v1"


def test_http_smoke_validates_positive_citations_and_no_data_fallback() -> None:
    opener = RecordingOpener(
        [FakeResponse(_envelope(_positive_data())), FakeResponse(_envelope(_no_data()))]
    )

    report = run_agent_runtime_smoke(
        base_url="http://agent-runtime.test:8000",
        definition=_definition(),
        opener=opener,
    )

    assert report.positive_status == "SUCCESS"
    assert report.positive_result_count == 3
    assert report.no_data_status == "NO_DATA"
    assert report.no_data_result_count == 0
    assert report.no_data_fallback_present is True
    assert [request[0] for request in opener.requests] == [
        "http://agent-runtime.test:8000/api/v1/rag/retrievals",
        "http://agent-runtime.test:8000/api/v1/rag/retrievals",
    ]
    assert opener.requests[0][2]["query"] == "positive configured query"
    assert opener.requests[1][2]["query"] == "negative configured query"


def test_unreachable_agent_runtime_fails_smoke() -> None:
    def unavailable(request: Any, *, timeout: float) -> Any:
        raise urllib.error.URLError("synthetic unavailable")

    with pytest.raises(SmokeTestError, match="failed"):
        run_agent_runtime_smoke(
            base_url="http://agent-runtime.test:8000",
            definition=_definition(),
            opener=unavailable,
        )


def test_incomplete_positive_citation_fails_smoke() -> None:
    positive = _positive_data()
    positive["results"][0]["section"] = None
    opener = RecordingOpener([FakeResponse(_envelope(positive))])

    with pytest.raises(SmokeTestError, match="citation field"):
        run_agent_runtime_smoke(
            base_url="http://agent-runtime.test:8000",
            definition=_definition(),
            opener=opener,
        )


def test_no_data_case_must_not_return_success_results() -> None:
    wrong_no_data = _positive_data()
    wrong_no_data["request_id"] = "rag-smoke-no-data"
    opener = RecordingOpener(
        [FakeResponse(_envelope(_positive_data())), FakeResponse(_envelope(wrong_no_data))]
    )

    with pytest.raises(SmokeTestError, match="did not return NO_DATA"):
        run_agent_runtime_smoke(
            base_url="http://agent-runtime.test:8000",
            definition=_definition(),
            opener=opener,
        )
