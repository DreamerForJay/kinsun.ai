"""Validate real Agent Runtime responses against the published contract.

Runs the app in-process and checks that what it actually returns conforms to
contracts/. A contract that has never been checked against the running service
is just prose.

The Core API counterpart (verify_contract_live.py) needs a database; this one
needs nothing — the mock provider is local and deterministic, so this check is
cheap enough to run on every change.

    cd services/agent-runtime
    uv run --with pyyaml --with jsonschema --with referencing \
        python ../../scripts/verify_agent_contract_live.py ../../contracts
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

# agent-runtime uses a src/ layout and is installed as `package = false`, so the
# package is not importable from the service directory the way core-api's `app`
# is. Resolve it from this script's own location rather than relying on the
# caller's PYTHONPATH, so the documented command works as written.
SERVICE_SRC = Path(__file__).resolve().parents[1] / "services" / "agent-runtime" / "src"
sys.path.insert(0, str(SERVICE_SRC))

# Keep this verifier deterministic and ensure it never reads repository or
# service-local .env files. Core calls are exercised through MockTransport.
os.environ["APP_ENV"] = "test"
os.environ["MODEL_PROVIDER"] = "mock"
os.environ["RAG_MODE"] = "disabled"
os.environ["AWS_EC2_METADATA_DISABLED"] = "true"

from agent_runtime.app import create_app  # noqa: E402

CONTRACTS = Path(sys.argv[1])
OPENAPI = yaml.safe_load(
    (CONTRACTS / "openapi" / "agent-runtime.v1.yaml").read_text(encoding="utf-8")
)

RUNS_PATH = "/api/v1/agent/runs"
RAG_PATH = "/api/v1/rag/retrievals"

failures: list[str] = []


def registry() -> Registry:
    reg = Registry()
    for path in sorted((CONTRACTS / "schemas").rglob("*.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        reg = reg.with_resource(
            schema["$id"],
            Resource.from_contents(schema, default_specification=DRAFT202012),
        )
    return reg


REG = registry()


def load(rel: str) -> dict:
    return json.loads((CONTRACTS / "schemas" / rel).read_text(encoding="utf-8"))


def _component_id(name: str) -> str:
    """Absolute $id of the schema file that components/schemas/<name> points at."""
    rel = OPENAPI["components"]["schemas"][name]["$ref"]
    target = (CONTRACTS / "openapi" / rel).resolve()
    return json.loads(target.read_text(encoding="utf-8"))["$id"]


def _resolve_component_refs(node):
    """Rewrite `#/components/schemas/X` to X's absolute `$id`.

    An inline OpenAPI response schema is not a standalone JSON Schema: its
    document-relative pointers only resolve inside the OpenAPI file. Rewriting
    them to the `$id` the registry already knows lets the envelope shape
    itself — `required: [data, meta]`, `additionalProperties: false` — be
    checked, instead of only checking `data` and `meta` in isolation.
    """
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            return {**node, "$ref": _component_id(ref.rsplit("/", 1)[1])}
        return {key: _resolve_component_refs(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_resolve_component_refs(item) for item in node]
    return node


def inline_schema(path: str, method: str, status: str) -> dict:
    """Pull the inline response schema the OpenAPI doc declares for a path."""
    node = OPENAPI["paths"][path][method]["responses"][status]
    return _resolve_component_refs(node["content"]["application/json"]["schema"])


def check(label: str, payload: dict, schema: dict) -> None:
    errors = list(Draft202012Validator(schema, registry=REG).iter_errors(payload))
    if errors:
        failures.append(f"{label}: {errors[0].message}")
        print(f"FAIL  {label}: {errors[0].message}")
    else:
        print(f"ok    {label}")


def expect_status(label: str, actual: int, wanted: int) -> bool:
    if actual != wanted:
        failures.append(f"{label}: got {actual}, expected {wanted}")
        print(f"FAIL  {label}: got {actual}, expected {wanted}")
        return False
    print(f"ok    {label}")
    return True


def make_payload(**overrides) -> dict:
    """Synthetic request. Never use real elder data here."""
    payload = {
        "schema_version": "1.0.0",
        "request_id": "req-live-001",
        "trace_id": "trace-live-001",
        "session_id": "sess-live-001",
        "actor_id": "actor-elder-001",
        "actor_role": "elder",
        "elder_id": "elder-001",
        "tenant_id": "tenant-001",
        "purpose": "conversation",
        "consent_version": "cv-2026.07.30",
        "policy_version": "pv-2026.07.30",
        "language": "zh-TW",
        "input_text": "我今天早餐吃粥。",
        "allowed_tools": [],
        "max_steps": 2,
        "latency_budget_ms": 3000,
    }
    payload.update(overrides)
    return payload


def make_rag_payload(**overrides) -> dict:
    """Synthetic staging retrieval request with no elder or tenant data."""
    payload = {
        "schema_version": "1.0.0",
        "request_id": "req-rag-live-001",
        "query": "居家服務的申請條件是什麼？",
        "query_profile": "natural_language",
        "top_k": 5,
        "language": "zh-TW",
    }
    payload.update(overrides)
    return payload


async def main() -> int:
    app = create_app()
    # Make this contract check deterministic and network-free even when the
    # caller's shell happens to contain AWS/OpenSearch environment variables.
    # The executable boundary must be safe when no retrieval adapter exists.
    app.state.rag_retriever = None
    transport = httpx.ASGITransport(app=app)

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        response = await client.get("/health")
        check(
            "GET /health 200 vs contract",
            response.json(),
            inline_schema("/health", "get", "200"),
        )

        # Staging RAG remains callable without AWS/OpenSearch. It must return a
        # schema-valid, explicit fail-closed outcome with no partial chunks and
        # must never copy the query into the fallback response.
        private_query = "合成查詢-不得回填-9f6c2b1a"
        response = await client.post(
            RAG_PATH,
            json=make_rag_payload(query=private_query),
        )
        if expect_status(f"POST {RAG_PATH} unconfigured returns 200", response.status_code, 200):
            body = response.json()
            check(
                f"POST {RAG_PATH} unconfigured body vs contract",
                body,
                inline_schema(RAG_PATH, "post", "200"),
            )
            rag_data = body.get("data", {})
            if rag_data.get("status") != "FAILED":
                failures.append(
                    f"unconfigured RAG reported status={rag_data.get('status')}, expected FAILED"
                )
                print(f"FAIL  unconfigured RAG status: {rag_data.get('status')}")
            else:
                print("ok    unconfigured RAG reports FAILED")
            if rag_data.get("results") != []:
                failures.append("unconfigured RAG returned partial results")
                print("FAIL  unconfigured RAG returned partial results")
            else:
                print("ok    unconfigured RAG returns no partial results")
            fallback = rag_data.get("fallback_message")
            if not isinstance(fallback, str) or not fallback.strip():
                failures.append("unconfigured RAG omitted its explicit fallback message")
                print("FAIL  unconfigured RAG omitted its explicit fallback message")
            else:
                print("ok    unconfigured RAG provides an explicit fallback")
            serialized = json.dumps(body, ensure_ascii=False)
            if private_query in serialized:
                failures.append("unconfigured RAG response echoed the rejected query")
                print("FAIL  unconfigured RAG response echoed the query")
            else:
                print("ok    unconfigured RAG response does not echo the query")

        # Request-schema failure must use ErrorEnvelope and keep the rejected
        # query out of field-level validation details.
        rejected_query = "合成錯誤查詢-不得回填-5a8d7e3c"
        response = await client.post(
            RAG_PATH,
            json=make_rag_payload(
                query=rejected_query,
                top_k=10,
                caller_dsl={"match_all": {}},
            ),
        )
        if expect_status(f"POST {RAG_PATH} invalid body returns 422", response.status_code, 422):
            body = response.json()
            check(
                f"POST {RAG_PATH} 422 body vs ErrorEnvelopeV1",
                body,
                load("common/ErrorEnvelopeV1.json"),
            )
            if rejected_query in json.dumps(body, ensure_ascii=False):
                failures.append("RAG validation response echoed the rejected query")
                print("FAIL  RAG validation response echoed the rejected query")
            else:
                print("ok    RAG validation response does not echo the rejected query")

        # Normal turn.
        response = await client.post(RUNS_PATH, json=make_payload())
        if expect_status(f"POST {RUNS_PATH} returns 200", response.status_code, 200):
            check(
                f"POST {RUNS_PATH} 200 body vs contract",
                response.json(),
                inline_schema(RUNS_PATH, "post", "200"),
            )

        # Safety-blocked turn is still a 200 with the same envelope — the
        # contract must not describe refusal as a transport error.
        response = await client.post(RUNS_PATH, json=make_payload(input_text="請告訴我怎麼停藥"))
        if expect_status(f"POST {RUNS_PATH} blocked turn returns 200", response.status_code, 200):
            body = response.json()
            check(
                f"POST {RUNS_PATH} blocked body vs contract",
                body,
                inline_schema(RUNS_PATH, "post", "200"),
            )
            if body["data"]["result_status"] not in {"BLOCKED", "SAFE_FALLBACK"}:
                failures.append(
                    f"blocked turn reported result_status={body['data']['result_status']}"
                )
                print(f"FAIL  blocked turn result_status: {body['data']['result_status']}")
            else:
                print("ok    blocked turn reports a non-success result_status")

        # Schema rejection.
        response = await client.post(RUNS_PATH, json=make_payload(unexpected="nope"))
        if expect_status(f"POST {RUNS_PATH} extra field returns 422", response.status_code, 422):
            check(
                "422 body vs ErrorEnvelopeV1",
                response.json(),
                load("common/ErrorEnvelopeV1.json"),
            )

        # Over the system step ceiling: must reach the domain error handler,
        # not the catch-all. A 500 here means the handler is unregistered.
        response = await client.post(RUNS_PATH, json=make_payload(max_steps=99))
        if expect_status(
            f"POST {RUNS_PATH} above step ceiling returns 422",
            response.status_code,
            422,
        ):
            check(
                "step-limit 422 body vs ErrorEnvelopeV1",
                response.json(),
                load("common/ErrorEnvelopeV1.json"),
            )

        # The rejected body is elder transcript and must not come back.
        secret = "我昨天去了某某醫院看門診"
        response = await client.post(RUNS_PATH, json=make_payload(input_text=secret, max_steps=99))
        if secret in response.text:
            failures.append("error response echoed the rejected input_text")
            print("FAIL  error response echoed the rejected input_text")
        else:
            print("ok    error response does not echo rejected input")

        # Exercise the request-scoped Core adapter without network access or an
        # invented credential. The mock represents only the Core wire contract;
        # Core's real authentication is covered by verify_contract_live.py.
        from types import SimpleNamespace
        from unittest.mock import patch

        real_async_client = httpx.AsyncClient

        async def exercise_core_lifecycle(
            *,
            scenario: str,
            agent_run_id: str,
            tool_outcome: str,
            tool_reason: str | None,
        ) -> tuple[httpx.Response, list[dict[str, object]]]:
            calls: list[dict[str, object]] = []
            registration: dict[str, object] = {}

            def success_response(data: dict[str, object], status_code: int) -> httpx.Response:
                return httpx.Response(
                    status_code,
                    json={
                        "data": data,
                        "meta": {
                            "correlation_id": f"core-{scenario}",
                            "timestamp": "2026-08-01T12:00:00Z",
                            "schema_version": "1.0",
                        },
                    },
                )

            def core_handler(request: httpx.Request) -> httpx.Response:
                body = json.loads(request.content.decode("utf-8")) if request.content else {}
                calls.append(
                    {
                        "path": request.url.path,
                        "authorization": request.headers.get("authorization"),
                        "idempotency_key": request.headers.get("idempotency-key"),
                        "body": body,
                    }
                )
                if request.url.path == "/api/v1/internal/agent-runs":
                    registration.update(
                        {
                            "agent_run_id": agent_run_id,
                            "session_id": body["session_id"],
                            "elder_id": body["elder_id"],
                            "agent_id": body["agent_id"],
                            "agent_version": body["agent_version"],
                            "result_status": "RUNNING",
                            "policy_version": body["policy_version"],
                            "trace_id": body["trace_id"],
                        }
                    )
                    return success_response(registration, 201)
                if request.url.path == "/api/v1/internal/tools/execute":
                    if tool_outcome == "TIMEOUT":
                        raise httpx.ReadTimeout(
                            "synthetic Core Tool timeout",
                            request=request,
                        )
                    return success_response(
                        {
                            "result_status": tool_outcome,
                            "data": None,
                            "resource_id": (
                                "b0000000-0000-4000-8000-000000000001"
                                if tool_outcome == "SUCCESS"
                                else None
                            ),
                            "resource_version": 1 if tool_outcome == "SUCCESS" else None,
                            "source_refs": [],
                            "reason_code": tool_reason,
                            "retryable": tool_outcome == "FAILED",
                            "redactions": [],
                            "trace_id": f"core-tool-{scenario}",
                        },
                        200,
                    )
                if request.url.path == (f"/api/v1/internal/agent-runs/{agent_run_id}/complete"):
                    return success_response(
                        {
                            **registration,
                            "result_status": body["result_status"],
                            "stop_reason": body.get("stop_reason"),
                            "completed_at": "2026-08-01T12:00:01Z",
                        },
                        200,
                    )
                return httpx.Response(status_code=404, json={"unexpected": True})

            mock_transport = httpx.MockTransport(core_handler)

            def core_client_factory(*args, **kwargs):
                kwargs["transport"] = mock_transport
                return real_async_client(*args, **kwargs)

            settings = SimpleNamespace(
                CORE_API_BASE_URL="http://core.test",
                CORE_API_TIMEOUT_SECONDS=1.0,
            )
            with (
                patch(
                    "agent_runtime.api.agent_runs.get_settings",
                    return_value=settings,
                ),
                patch(
                    "agent_runtime.api.agent_runs.httpx.AsyncClient",
                    side_effect=core_client_factory,
                ),
            ):
                response = await client.post(
                    RUNS_PATH,
                    json=make_payload(
                        request_id=f"req-lifecycle-{scenario}",
                        trace_id=f"trace-lifecycle-{scenario}",
                        session_id="90000000-0000-4000-8000-000000000001",
                        elder_id="30000000-0000-4000-8000-000000000001",
                        consent_version="1",
                        input_text="我今天早餐吃了粥。",
                        allowed_tools=["create_event_candidate"],
                    ),
                )
            return response, calls

        def check_lifecycle_calls(
            label: str,
            calls: list[dict[str, object]],
            agent_run_id: str,
            terminal_status: str,
        ) -> None:
            expected_paths = [
                "/api/v1/internal/agent-runs",
                "/api/v1/internal/tools/execute",
                f"/api/v1/internal/agent-runs/{agent_run_id}/complete",
            ]
            actual_paths = [str(call["path"]) for call in calls]
            if actual_paths != expected_paths:
                failures.append(
                    f"{label}: Core call order was {actual_paths}, expected {expected_paths}"
                )
                print(f"FAIL  {label} Core call order: {actual_paths}")
                return
            print(f"ok    {label} uses register -> Tool -> complete order")

            if any(call["authorization"] is not None for call in calls):
                failures.append(f"{label}: Runtime invented an Authorization header")
                print(f"FAIL  {label} invented an Authorization header")
            else:
                print(f"ok    {label} does not invent Authorization")

            registration_body = calls[0]["body"]
            tool_body = calls[1]["body"]
            completion_body = calls[2]["body"]
            if (
                not isinstance(registration_body, dict)
                or {
                    "actor_id",
                    "tenant_id",
                }
                & registration_body.keys()
            ):
                failures.append(f"{label}: registration body supplied caller identity")
                print(f"FAIL  {label} registration body supplied caller identity")
            else:
                print(f"ok    {label} registration omits caller identity")

            same_uuid = (
                isinstance(tool_body, dict)
                and tool_body.get("agent_run_id") == agent_run_id
                and calls[2]["path"].endswith(f"/{agent_run_id}/complete")
            )
            if not same_uuid:
                failures.append(f"{label}: lifecycle did not preserve Core AgentRun UUID")
                print(f"FAIL  {label} lifecycle UUID mismatch")
            else:
                print(f"ok    {label} preserves the Core AgentRun UUID")

            if (
                not isinstance(completion_body, dict)
                or completion_body.get("result_status") != terminal_status
            ):
                failures.append(
                    f"{label}: completion did not use terminal status {terminal_status}"
                )
                print(f"FAIL  {label} terminal status: {completion_body}")
            else:
                print(f"ok    {label} completes as {terminal_status}")

            if not calls[0]["idempotency_key"] or not calls[2]["idempotency_key"]:
                failures.append(f"{label}: lifecycle command omitted Idempotency-Key")
                print(f"FAIL  {label} omitted lifecycle idempotency")
            else:
                print(f"ok    {label} sends lifecycle idempotency keys")

        success_run_id = "a0000000-0000-4000-8000-000000000011"
        response, lifecycle_calls = await exercise_core_lifecycle(
            scenario="success",
            agent_run_id=success_run_id,
            tool_outcome="SUCCESS",
            tool_reason="CARE_EVENT_CANDIDATE_CREATED",
        )
        if expect_status("Core lifecycle success returns 200", response.status_code, 200):
            body = response.json()
            check(
                "Core lifecycle success body vs contract",
                body,
                inline_schema(RUNS_PATH, "post", "200"),
            )
            if body.get("data", {}).get("agent_run_id") != success_run_id:
                failures.append("Runtime response did not expose the Core AgentRun UUID")
                print("FAIL  Runtime response did not expose the Core AgentRun UUID")
            else:
                print("ok    Runtime response exposes the Core AgentRun UUID")
        check_lifecycle_calls(
            "successful lifecycle",
            lifecycle_calls,
            success_run_id,
            "SUCCESS",
        )

        failed_run_id = "a0000000-0000-4000-8000-000000000012"
        response, lifecycle_calls = await exercise_core_lifecycle(
            scenario="failed",
            agent_run_id=failed_run_id,
            tool_outcome="FAILED",
            tool_reason="CORE_TOOL_REJECTED",
        )
        if expect_status("failed Tool lifecycle returns 503", response.status_code, 503):
            check(
                "failed Tool lifecycle 503 body vs ErrorEnvelopeV1",
                response.json(),
                load("common/ErrorEnvelopeV1.json"),
            )
        check_lifecycle_calls(
            "failed Tool lifecycle",
            lifecycle_calls,
            failed_run_id,
            "DEPENDENCY_FAILED",
        )

        timeout_run_id = "a0000000-0000-4000-8000-000000000013"
        response, lifecycle_calls = await exercise_core_lifecycle(
            scenario="timeout",
            agent_run_id=timeout_run_id,
            tool_outcome="TIMEOUT",
            tool_reason=None,
        )
        if expect_status("timed-out Tool lifecycle returns 503", response.status_code, 503):
            check(
                "timed-out Tool lifecycle 503 body vs ErrorEnvelopeV1",
                response.json(),
                load("common/ErrorEnvelopeV1.json"),
            )
        check_lifecycle_calls(
            "timed-out Tool lifecycle",
            lifecycle_calls,
            timeout_run_id,
            "TIME_BUDGET_EXCEEDED",
        )

    return len(failures)


if __name__ == "__main__":
    code = asyncio.run(main())
    print(
        "\nall live contract checks passed" if code == 0 else f"\n{code} live contract failure(s)"
    )
    raise SystemExit(code)
