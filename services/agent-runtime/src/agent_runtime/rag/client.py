from __future__ import annotations

import asyncio
import inspect
from collections.abc import Mapping
from typing import Protocol, cast
from urllib.parse import urlparse

import boto3
from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection

from agent_runtime.rag.models import HybridSearchPlan, OpenSearchConnectionSettings


class OpenSearchClientError(RuntimeError):
    """OpenSearch did not return a usable search response."""


class OpenSearchTransport(Protocol):
    def search(self, **kwargs: object) -> Mapping[str, object]: ...


class OpenSearchClient:
    """Small adapter around an injected opensearch-py-compatible transport."""

    def __init__(self, transport: OpenSearchTransport) -> None:
        self._transport = transport

    async def search(self, plan: HybridSearchPlan) -> list[Mapping[str, object]]:
        response = await asyncio.to_thread(
            self._transport.search,
            index=plan.index_alias,
            body=plan.body,
            params={"search_pipeline": plan.search_pipeline},
        )
        if inspect.isawaitable(response):
            response = await response
        if not isinstance(response, Mapping):
            raise OpenSearchClientError("OpenSearch response must be an object")
        hits_container = response.get("hits")
        if not isinstance(hits_container, Mapping):
            raise OpenSearchClientError("OpenSearch response is missing hits")
        hits = hits_container.get("hits")
        if not isinstance(hits, list):
            raise OpenSearchClientError("OpenSearch hits must be a list")
        if any(not isinstance(hit, Mapping) for hit in hits):
            raise OpenSearchClientError("OpenSearch returned a malformed hit")
        return cast(list[Mapping[str, object]], hits)


def build_opensearch_transport(settings: OpenSearchConnectionSettings) -> OpenSearchTransport:
    """Build a SigV4-authenticated OpenSearch transport for the configured staging host."""

    parsed = _parse_host(settings.host)
    session = boto3.Session(region_name=settings.region)
    credentials = session.get_credentials()
    if credentials is None:
        raise OpenSearchClientError("AWS credentials are unavailable from the provider chain")
    service = "aoss" if ".aoss." in parsed.hostname else "es"
    auth = AWSV4SignerAuth(credentials, settings.region, service)
    transport = OpenSearch(
        hosts=[
            {
                "host": parsed.hostname,
                "port": parsed.port or (443 if parsed.scheme == "https" else 80),
            }
        ],
        http_auth=auth,
        use_ssl=parsed.scheme == "https",
        verify_certs=parsed.scheme == "https",
        connection_class=RequestsHttpConnection,
    )
    return cast(OpenSearchTransport, transport)


def build_opensearch_client(settings: OpenSearchConnectionSettings) -> OpenSearchClient:
    return OpenSearchClient(build_opensearch_transport(settings))


def _parse_host(host: str):
    candidate = host if "://" in host else f"https://{host}"
    parsed = urlparse(candidate)
    if (
        parsed.hostname is None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise OpenSearchClientError("OPENSEARCH_HOST must contain only a host and optional port")
    if parsed.scheme not in {"http", "https"}:
        raise OpenSearchClientError("OPENSEARCH_HOST must use http or https")
    return parsed
