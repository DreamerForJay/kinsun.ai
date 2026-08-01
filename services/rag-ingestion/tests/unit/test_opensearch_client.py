from __future__ import annotations

from typing import Any

import pytest

from rag_ingestion.opensearch_client import (
    OpenSearchGateway,
    OpenSearchOperationError,
    infer_opensearch_service,
)


class FakeTransport:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def perform_request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.calls.append((method, path, body))
        return self.response


class FakeRawClient:
    def __init__(self, response: dict[str, Any]) -> None:
        self.transport = FakeTransport(response)


class FakeBulkRawClient:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def bulk(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self.response


def test_bulk_create_omits_the_refresh_policy_serverless_rejects() -> None:
    client = FakeBulkRawClient({"errors": False, "items": [{"create": {"status": 201}}]})

    created = OpenSearchGateway(client).bulk_create(
        "synthetic-staging-v1", [("chunk-1", {"chunk_id": "chunk-1"})]
    )

    assert created == 1
    assert "refresh" not in client.calls[0]


def test_from_aws_sets_a_timeout_large_enough_for_a_full_bulk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import opensearchpy

    captured: dict[str, Any] = {}

    class FakeOpenSearch:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    class FakeSession:
        def get_credentials(self) -> object:
            return object()

    monkeypatch.setattr(opensearchpy, "OpenSearch", FakeOpenSearch)
    monkeypatch.setattr(opensearchpy, "AWSV4SignerAuth", lambda *args: object())

    OpenSearchGateway.from_aws(
        host="https://collection.us-west-2.aoss.amazonaws.com",
        region="us-west-2",
        session=FakeSession(),
    )

    assert captured["timeout"] >= 60


def test_search_pipeline_requires_acknowledgement() -> None:
    client = FakeRawClient({"acknowledged": False})

    with pytest.raises(OpenSearchOperationError, match="acknowledge"):
        OpenSearchGateway(client).put_search_pipeline(
            "synthetic-staging-v1", {"phase_results_processors": []}
        )


def test_search_pipeline_put_uses_configured_name_and_body() -> None:
    client = FakeRawClient({"acknowledged": True})
    body = {"phase_results_processors": []}

    OpenSearchGateway(client).put_search_pipeline("synthetic-staging-v1", body)

    assert client.transport.calls == [("PUT", "/_search/pipeline/synthetic-staging-v1", body)]


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("https://collection.us-east-1.aoss.amazonaws.com", "aoss"),
        ("search-domain.us-east-1.es.amazonaws.com", "es"),
        ("localhost", "es"),
    ],
)
def test_signing_service_is_inferred_from_hostname(host: str, expected: str) -> None:
    assert infer_opensearch_service(host) == expected
