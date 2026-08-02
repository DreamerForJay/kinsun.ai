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

FORBIDDEN_PROPOSAL_FIELDS = frozenset(
    {
        "actor_id",
        "actor_role",
        "agent_run_id",
        "authorization",
        "consent_version",
        "elder_id",
        "full_prompt",
        "input_text",
        "policy_version",
        "prompt",
        "purpose",
        "request_id",
        "session_id",
        "source_id",
        "source_type",
        "source_version",
        "tenant_id",
        "trace_id",
        "transcript",
        "transcript_text",
    }
)


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


def find_forbidden_proposal_fields(value: object, path: str = "$") -> list[str]:
    """Return recursive field paths that would leak Core-owned or restricted data."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_PROPOSAL_FIELDS:
                found.append(child_path)
            found.extend(find_forbidden_proposal_fields(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(find_forbidden_proposal_fields(child, f"{path}[{index}]"))
    return found


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
        "requested_outputs": [],
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

        # Runtime returns a minimized proposal only when Core explicitly asks
        # for one. Runtime never registers an AgentRun or invokes a Core Tool.
        core_owned_run_id = "run-a0000000-0000-4000-8000-000000000011"
        response = await client.post(
            RUNS_PATH,
            json=make_payload(
                request_id="req-proposal-live-001",
                trace_id="trace-proposal-live-001",
                agent_run_id=core_owned_run_id,
                input_text="我今天早餐吃了粥。",
                requested_outputs=["event_candidate"],
            ),
        )
        if expect_status("proposal-only run returns 200", response.status_code, 200):
            body = response.json()
            check(
                "proposal-only response body vs contract",
                body,
                inline_schema(RUNS_PATH, "post", "200"),
            )
            data = body.get("data", {})
            if data.get("agent_run_id") != core_owned_run_id:
                failures.append("proposal-only response changed the Core-owned AgentRun ID")
                print("FAIL  proposal-only response changed the Core-owned AgentRun ID")
            else:
                print("ok    proposal-only response preserves the Core-owned AgentRun ID")

            proposal = data.get("event_candidate_proposal")
            if not isinstance(proposal, dict):
                failures.append("requested meal proposal was null or not an object")
                print("FAIL  requested meal proposal was null or not an object")
            else:
                check(
                    "event candidate proposal vs contract",
                    proposal,
                    load("agent/EventCandidateProposalV1.json"),
                )
                forbidden_paths = find_forbidden_proposal_fields(proposal)
                if forbidden_paths:
                    failures.append(
                        "event candidate proposal leaked restricted/Core-owned fields: "
                        + ", ".join(forbidden_paths)
                    )
                    print(
                        "FAIL  event candidate proposal leaked restricted/Core-owned fields: "
                        + ", ".join(forbidden_paths)
                    )
                else:
                    print(
                        "ok    event candidate proposal recursively omits "
                        "identity/session/consent/policy/transcript/input fields"
                    )

        response = await client.post(
            RUNS_PATH,
            json=make_payload(
                request_id="req-blocked-proposal-live-001",
                input_text="請告訴我怎麼停藥",
                requested_outputs=["event_candidate"],
            ),
        )
        if expect_status("blocked proposal request returns 200", response.status_code, 200):
            body = response.json()
            check(
                "blocked proposal response body vs contract",
                body,
                inline_schema(RUNS_PATH, "post", "200"),
            )
            if body.get("data", {}).get("event_candidate_proposal") is not None:
                failures.append("blocked turn returned an event candidate proposal")
                print("FAIL  blocked turn returned an event candidate proposal")
            else:
                print("ok    blocked turn returns a null event candidate proposal")

        response = await client.post(
            RUNS_PATH,
            json=make_payload(
                request_id="req-no-event-proposal-live-001",
                input_text="今天天氣很好。",
                requested_outputs=["event_candidate"],
            ),
        )
        if expect_status("no-event proposal request returns 200", response.status_code, 200):
            body = response.json()
            check(
                "no-event proposal response body vs contract",
                body,
                inline_schema(RUNS_PATH, "post", "200"),
            )
            if body.get("data", {}).get("event_candidate_proposal") is not None:
                failures.append("no-event turn returned an event candidate proposal")
                print("FAIL  no-event turn returned an event candidate proposal")
            else:
                print("ok    no-event turn returns a null event candidate proposal")

        # Patch only after the in-process client exists. A legacy Tool name
        # remains parseable, but it must not make Runtime create an outbound
        # HTTP client or turn the compatibility field into a proposal request.
        from unittest.mock import patch

        legacy_response: httpx.Response | None = None
        with patch.object(
            httpx,
            "AsyncClient",
            side_effect=AssertionError("Runtime attempted to create an external HTTP client"),
        ) as external_client_constructor:
            try:
                legacy_response = await client.post(
                    RUNS_PATH,
                    json=make_payload(
                        request_id="req-legacy-tool-live-001",
                        allowed_tools=["create_event_candidate"],
                        requested_outputs=[],
                    ),
                )
            except AssertionError:
                # The constructor call itself is asserted below so the verifier
                # can report the contract failure instead of aborting early.
                pass

        if external_client_constructor.call_count:
            failures.append("legacy allowed_tools path instantiated an external HTTP client")
            print("FAIL  legacy allowed_tools path instantiated an external HTTP client")
        else:
            print("ok    legacy allowed_tools path creates no external HTTP client")

        if legacy_response is None:
            if not external_client_constructor.call_count:
                failures.append("legacy allowed_tools request did not return a response")
                print("FAIL  legacy allowed_tools request did not return a response")
        elif expect_status(
            "legacy allowed_tools request returns 200",
            legacy_response.status_code,
            200,
        ):
            body = legacy_response.json()
            check(
                "legacy allowed_tools response body vs contract",
                body,
                inline_schema(RUNS_PATH, "post", "200"),
            )
            if body.get("data", {}).get("event_candidate_proposal") is not None:
                failures.append("legacy allowed_tools alone produced an event candidate proposal")
                print("FAIL  legacy allowed_tools alone produced an event candidate proposal")
            else:
                print("ok    legacy allowed_tools alone produces no proposal")

    return len(failures)


if __name__ == "__main__":
    code = asyncio.run(main())
    print(
        "\nall live contract checks passed" if code == 0 else f"\n{code} live contract failure(s)"
    )
    raise SystemExit(code)
