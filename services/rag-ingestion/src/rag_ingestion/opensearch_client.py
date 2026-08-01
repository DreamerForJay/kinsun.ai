"""Small injectable OpenSearch adapter used by the offline service."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote, urlsplit

# A full staging bulk is several megabytes and has been measured at ~24s, well
# past opensearch-py's 10s default. Serverless TLS handshakes are also slow
# enough under load to exhaust that default on plain metadata reads.
DEFAULT_REQUEST_TIMEOUT_SECONDS = 120


class OpenSearchOperationError(RuntimeError):
    """Raised when OpenSearch does not fully acknowledge an operation."""


class BulkOperationError(OpenSearchOperationError):
    """Raised when a bulk request is accepted but individual items failed.

    The message names failed document IDs, so it stays out of command logs.
    ``error_types`` carries only OpenSearch's symbolic error classes, which
    contain no indexed content and are therefore safe to report.
    """

    def __init__(self, message: str, *, error_types: tuple[str, ...] = ()) -> None:
        self.error_types = error_types
        super().__init__(message)


class RawOpenSearchClient(Protocol):
    indices: Any
    transport: Any

    def bulk(self, **kwargs: Any) -> dict[str, Any]: ...

    def count(self, **kwargs: Any) -> dict[str, Any]: ...

    def search(self, **kwargs: Any) -> dict[str, Any]: ...

    def mget(self, **kwargs: Any) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class IndexedDocument:
    document_id: str
    source: dict[str, Any]


class OpenSearchGateway:
    def __init__(self, client: RawOpenSearchClient) -> None:
        self._client = client

    @classmethod
    def from_aws(
        cls,
        *,
        host: str,
        region: str,
        service: str | None = None,
        session: Any | None = None,
        timeout: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> OpenSearchGateway:
        if not host.strip() or not region.strip():
            raise ValueError("OpenSearch host and AWS region are required")
        parsed = urlsplit(host if "://" in host else f"https://{host}")
        if parsed.username or parsed.password or not parsed.hostname:
            raise ValueError("OpenSearch host must not contain credentials")
        signing_service = service or infer_opensearch_service(parsed.hostname)
        if signing_service not in {"aoss", "es"}:
            raise ValueError("OpenSearch signing service must be aoss or es")
        if session is None:
            import boto3

            session = boto3.Session()
        credentials = session.get_credentials()
        if credentials is None:
            raise OpenSearchOperationError("AWS credentials are unavailable")

        from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection

        auth = AWSV4SignerAuth(credentials, region, signing_service)
        client = OpenSearch(
            hosts=[{"host": parsed.hostname, "port": parsed.port or 443}],
            http_auth=auth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            pool_maxsize=20,
            timeout=timeout,
        )
        return cls(client)

    def index_exists(self, index_name: str) -> bool:
        return bool(self._client.indices.exists(index=index_name))

    def create_index(self, index_name: str, body: dict[str, Any]) -> None:
        response = self._client.indices.create(index=index_name, body=body)
        if not isinstance(response, dict) or response.get("acknowledged") is not True:
            raise OpenSearchOperationError("OpenSearch did not acknowledge index creation")

    def delete_index(self, index_name: str) -> None:
        try:
            response = self._client.indices.delete(index=index_name)
        except Exception as exc:
            if getattr(exc, "status_code", None) == 404:
                return
            raise OpenSearchOperationError(
                f"cannot delete staging index: {type(exc).__name__}"
            ) from exc
        if isinstance(response, dict) and response.get("acknowledged") is False:
            raise OpenSearchOperationError("OpenSearch did not acknowledge staging rollback")

    def get_mapping(self, index_name: str) -> dict[str, Any]:
        response = self._client.indices.get_mapping(index=index_name)
        if not isinstance(response, dict):
            raise OpenSearchOperationError("OpenSearch mapping response must be an object")
        return response

    def set_alias(self, index_name: str, alias_name: str) -> None:
        actions: list[dict[str, Any]] = []
        try:
            current = self._client.indices.get_alias(name=alias_name)
        except Exception as exc:
            if getattr(exc, "status_code", None) != 404:
                raise OpenSearchOperationError(
                    f"cannot inspect OpenSearch alias: {type(exc).__name__}"
                ) from exc
            current = {}
        if isinstance(current, dict):
            actions.extend(
                {"remove": {"index": existing_index, "alias": alias_name}}
                for existing_index in current
                if existing_index != index_name
            )
        actions.append({"add": {"index": index_name, "alias": alias_name}})
        response = self._client.indices.update_aliases(body={"actions": actions})
        if not isinstance(response, dict) or response.get("acknowledged") is not True:
            raise OpenSearchOperationError("OpenSearch did not acknowledge alias update")

    def alias_targets(self, alias_name: str) -> tuple[str, ...]:
        try:
            response = self._client.indices.get_alias(name=alias_name)
        except Exception as exc:
            if getattr(exc, "status_code", None) == 404:
                return ()
            raise OpenSearchOperationError(
                f"cannot inspect OpenSearch alias: {type(exc).__name__}"
            ) from exc
        if not isinstance(response, dict):
            raise OpenSearchOperationError("OpenSearch alias response must be an object")
        targets: list[str] = []
        for index_name, details in response.items():
            aliases = details.get("aliases") if isinstance(details, dict) else None
            if isinstance(index_name, str) and isinstance(aliases, dict) and alias_name in aliases:
                targets.append(index_name)
        return tuple(sorted(targets))

    def get_search_pipeline(self, pipeline_name: str) -> dict[str, Any] | None:
        try:
            response = self._client.transport.perform_request(
                "GET", f"/_search/pipeline/{quote(pipeline_name, safe='')}"
            )
        except Exception as exc:
            if getattr(exc, "status_code", None) == 404:
                return None
            raise OpenSearchOperationError(
                f"cannot inspect OpenSearch search pipeline: {type(exc).__name__}"
            ) from exc
        if not isinstance(response, dict):
            raise OpenSearchOperationError("OpenSearch search-pipeline response is invalid")
        pipeline = response.get(pipeline_name)
        if not isinstance(pipeline, dict):
            raise OpenSearchOperationError("OpenSearch search pipeline is missing from response")
        return pipeline

    def put_search_pipeline(self, pipeline_name: str, body: dict[str, Any]) -> None:
        response = self._client.transport.perform_request(
            "PUT",
            f"/_search/pipeline/{quote(pipeline_name, safe='')}",
            body=body,
        )
        if not isinstance(response, dict) or response.get("acknowledged") is not True:
            raise OpenSearchOperationError(
                "OpenSearch did not acknowledge search-pipeline creation"
            )

    def delete_search_pipeline(self, pipeline_name: str) -> None:
        try:
            response = self._client.transport.perform_request(
                "DELETE", f"/_search/pipeline/{quote(pipeline_name, safe='')}"
            )
        except Exception as exc:
            if getattr(exc, "status_code", None) == 404:
                return
            raise OpenSearchOperationError(
                f"cannot delete OpenSearch search pipeline: {type(exc).__name__}"
            ) from exc
        if isinstance(response, dict) and response.get("acknowledged") is False:
            raise OpenSearchOperationError(
                "OpenSearch did not acknowledge search-pipeline rollback"
            )

    def bulk_create(
        self,
        index_name: str,
        documents: Sequence[tuple[str, dict[str, Any]]],
    ) -> int:
        body: list[dict[str, Any]] = []
        for document_id, document in documents:
            body.append({"create": {"_index": index_name, "_id": document_id}})
            body.append(document)
        # Serverless rejects the wait_for refresh policy with a 400 on every
        # item, so document visibility is awaited by BulkIngester instead.
        response = self._client.bulk(body=body)
        if not isinstance(response, dict):
            raise OpenSearchOperationError("OpenSearch bulk response must be an object")
        items = response.get("items")
        if response.get("errors") is not False or not isinstance(items, list):
            failed = _failed_bulk_ids(items)
            suffix = f" ({', '.join(failed[:3])})" if failed else ""
            raise BulkOperationError(
                f"OpenSearch bulk create was not fully successful{suffix}",
                error_types=_failed_bulk_error_types(items),
            )
        if len(items) != len(documents):
            raise OpenSearchOperationError("OpenSearch bulk response count does not match request")
        return len(items)

    def count_documents(self, index_name: str) -> int:
        response = self._client.count(index=index_name)
        count = response.get("count") if isinstance(response, dict) else None
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise OpenSearchOperationError("OpenSearch count response is invalid")
        return count

    def duplicate_chunk_ids(self, index_name: str) -> tuple[str, ...]:
        response = self._client.search(
            index=index_name,
            body={
                "size": 0,
                "aggs": {
                    "duplicate_chunk_ids": {
                        "terms": {"field": "chunk_id", "min_doc_count": 2, "size": 10000}
                    }
                },
            },
        )
        try:
            buckets = response["aggregations"]["duplicate_chunk_ids"]["buckets"]
        except (KeyError, TypeError) as exc:
            raise OpenSearchOperationError("OpenSearch duplicate-ID response is invalid") from exc
        if not isinstance(buckets, list):
            raise OpenSearchOperationError("OpenSearch duplicate-ID buckets must be an array")
        duplicates: list[str] = []
        for bucket in buckets:
            key = bucket.get("key") if isinstance(bucket, dict) else None
            if isinstance(key, str):
                duplicates.append(key)
        return tuple(duplicates)

    def fetch_documents(
        self, index_name: str, document_ids: Sequence[str], *, batch_size: int = 200
    ) -> tuple[IndexedDocument, ...]:
        fetched: list[IndexedDocument] = []
        for offset in range(0, len(document_ids), batch_size):
            batch = list(document_ids[offset : offset + batch_size])
            response = self._client.mget(
                index=index_name,
                body={"ids": batch},
                _source_includes=["chunk_id", "embedding"],
            )
            docs = response.get("docs") if isinstance(response, dict) else None
            if not isinstance(docs, list) or len(docs) != len(batch):
                raise OpenSearchOperationError("OpenSearch mget response count is invalid")
            for doc in docs:
                if not isinstance(doc, dict) or doc.get("found") is not True:
                    raise OpenSearchOperationError("OpenSearch mget did not find every document")
                document_id = doc.get("_id")
                source = doc.get("_source")
                if not isinstance(document_id, str) or not isinstance(source, dict):
                    raise OpenSearchOperationError("OpenSearch mget document is invalid")
                fetched.append(IndexedDocument(document_id=document_id, source=source))
        return tuple(fetched)

    def smoke_test_current_normal_rag(self, index_name: str) -> int:
        """Run a vector-free smoke query with the mandatory safety filters."""

        response = self._client.search(
            index=index_name,
            body={
                "size": 5,
                "_source": [
                    "chunk_id",
                    "document_name",
                    "section",
                    "page_start",
                    "page_end",
                    "source_url",
                    "current_status",
                    "stop_normal_rag",
                ],
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"current_status": "current"}},
                            {"term": {"stop_normal_rag": False}},
                        ]
                    }
                },
            },
        )
        try:
            hits = response["hits"]["hits"]
        except (KeyError, TypeError) as exc:
            raise OpenSearchOperationError("OpenSearch smoke-test response is invalid") from exc
        if not isinstance(hits, list):
            raise OpenSearchOperationError("OpenSearch smoke-test hits must be an array")
        for hit in hits:
            source = hit.get("_source") if isinstance(hit, dict) else None
            if not isinstance(source, dict):
                raise OpenSearchOperationError("OpenSearch smoke-test hit is invalid")
            if (
                source.get("current_status") != "current"
                or source.get("stop_normal_rag") is not False
            ):
                raise OpenSearchOperationError("OpenSearch smoke-test returned a blocked chunk")
            if not isinstance(source.get("chunk_id"), str) or not isinstance(
                source.get("document_name"), str
            ):
                raise OpenSearchOperationError("OpenSearch smoke-test hit has no citation identity")
        return len(hits)


def _failed_bulk_error_types(items: Any) -> tuple[str, ...]:
    """Collect distinct OpenSearch error classes from failed bulk items.

    Only the ``type`` field is read. Item ``reason`` text can quote the
    document that failed to parse, so it is never collected here.
    """

    if not isinstance(items, list):
        return ()
    error_types: set[str] = set()
    for item in items:
        action = item.get("create") if isinstance(item, dict) else None
        error = action.get("error") if isinstance(action, dict) else None
        error_type = error.get("type") if isinstance(error, dict) else None
        if isinstance(error_type, str) and error_type.isidentifier():
            error_types.add(error_type)
    return tuple(sorted(error_types))


def _failed_bulk_ids(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    failed: list[str] = []
    for item in items:
        action = item.get("create") if isinstance(item, dict) else None
        if isinstance(action, dict) and int(action.get("status", 500)) >= 300:
            document_id = action.get("_id")
            if isinstance(document_id, str):
                failed.append(document_id)
    return failed


def infer_opensearch_service(host: str) -> str:
    """Choose the AWS SigV4 service from the endpoint hostname."""

    hostname = urlsplit(host if "://" in host else f"https://{host}").hostname
    if not hostname:
        raise ValueError("OpenSearch hostname is required")
    return "aoss" if ".aoss." in hostname.casefold() else "es"
