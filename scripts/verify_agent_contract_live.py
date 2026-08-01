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

from agent_runtime.app import create_app  # noqa: E402

CONTRACTS = Path(sys.argv[1])
OPENAPI = yaml.safe_load(
    (CONTRACTS / "openapi" / "agent-runtime.v1.yaml").read_text(encoding="utf-8")
)

RUNS_PATH = "/api/v1/agent/runs"

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


async def main() -> int:
    app = create_app()
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
            check("422 body vs ErrorEnvelopeV1", response.json(), load("common/ErrorEnvelopeV1.json"))

        # Over the system step ceiling: must reach the domain error handler,
        # not the catch-all. A 500 here means the handler is unregistered.
        response = await client.post(RUNS_PATH, json=make_payload(max_steps=99))
        if expect_status(
            f"POST {RUNS_PATH} above step ceiling returns 422", response.status_code, 422
        ):
            check(
                "step-limit 422 body vs ErrorEnvelopeV1",
                response.json(),
                load("common/ErrorEnvelopeV1.json"),
            )

        # The rejected body is elder transcript and must not come back.
        secret = "我昨天去了某某醫院看門診"
        response = await client.post(
            RUNS_PATH, json=make_payload(input_text=secret, max_steps=99)
        )
        if secret in response.text:
            failures.append("error response echoed the rejected input_text")
            print("FAIL  error response echoed the rejected input_text")
        else:
            print("ok    error response does not echo rejected input")

    return len(failures)


if __name__ == "__main__":
    code = asyncio.run(main())
    print("\nall live contract checks passed" if code == 0 else f"\n{code} live contract failure(s)")
    raise SystemExit(code)
