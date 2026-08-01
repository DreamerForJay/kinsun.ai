"""Validate real Core API responses against the published contract.

Runs the app in-process and checks that what it actually returns conforms to
contracts/. A contract that has never been checked against the running service
is just prose.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

import httpx
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "services" / "core-api"))
# This verifier is specifically a no-authenticator fail-closed check. Make it
# deterministic even when the developer's local .env enables synthetic auth.
os.environ["FAKE_AUTH_ENABLED"] = "false"

from app.main import create_app  # noqa: E402 - path must be installed before app import

CONTRACTS = Path(sys.argv[1]).resolve()
OPENAPI = yaml.safe_load(
    (CONTRACTS / "openapi" / "core-api.v1.yaml").read_text(encoding="utf-8")
)

failures: list[str] = []


def registry() -> Registry:
    reg = Registry()
    for path in sorted((CONTRACTS / "schemas").rglob("*.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        reg = reg.with_resource(schema["$id"], Resource.from_contents(schema))
    return reg


REG = registry()


def load(rel: str) -> dict:
    return json.loads((CONTRACTS / "schemas" / rel).read_text(encoding="utf-8"))


def inline_schema(path: str, status: str, method: str = "get") -> dict:
    """Pull the inline response schema the OpenAPI doc declares for a path."""
    node = OPENAPI["paths"][path][method]["responses"][status]
    return node["content"]["application/json"]["schema"]


def check(label: str, payload: dict, schema: dict) -> None:
    errors = list(Draft202012Validator(schema, registry=REG).iter_errors(payload))
    if errors:
        failures.append(f"{label}: {errors[0].message}")
        print(f"FAIL  {label}: {errors[0].message}")
    else:
        print(f"ok    {label}")


async def main() -> int:
    app = create_app()
    runtime_openapi = app.openapi()
    methods = {"get", "post", "patch", "delete"}
    runtime_operations = {
        (path, method)
        for path, item in runtime_openapi["paths"].items()
        for method in item
        if method in methods
    }
    contracted_operations = {
        (path, method)
        for path, item in OPENAPI["paths"].items()
        for method in item
        if method in methods
    }
    if runtime_operations != contracted_operations:
        missing = sorted(runtime_operations - contracted_operations)
        stale = sorted(contracted_operations - runtime_operations)
        failures.append(
            f"OpenAPI/runtime operation mismatch: missing={missing}, stale={stale}"
        )
        print(
            f"FAIL  OpenAPI/runtime operation mismatch: missing={missing}, stale={stale}"
        )
    else:
        print(f"ok    all {len(runtime_operations)} runtime operations are contracted")

    transport = httpx.ASGITransport(app=app)

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        response = await client.get("/health")
        check(
            "GET /health 200 vs contract",
            response.json(),
            inline_schema("/health", "200"),
        )

        response = await client.get("/ready")
        check(
            "GET /ready 200 vs contract",
            response.json(),
            inline_schema("/ready", "200"),
        )

        # No credentials configured -> must fail closed as a contract-shaped 401.
        response = await client.get(
            "/api/v1/elders/2a6f9c31-8e47-4b52-9d10-3c8a7e5b1a40"
        )
        if response.status_code != 401:
            failures.append(
                f"protected route returned {response.status_code}, expected 401"
            )
            print(f"FAIL  protected route status: {response.status_code}")
        else:
            print("ok    protected route fails closed with 401")
        check(
            "401 body vs ErrorEnvelopeV1",
            response.json(),
            load("common/ErrorEnvelopeV1.json"),
        )

        response = await client.get("/api/v1/me")
        check(
            "GET /api/v1/me 401 body vs ErrorEnvelopeV1",
            response.json(),
            load("common/ErrorEnvelopeV1.json"),
        )

        response = await client.post(
            "/api/v1/voice-sessions/2a6f9c31-8e47-4b52-9d10-3c8a7e5b1a40/companion-turns",
            headers={"Idempotency-Key": "live-contract-companion-turn"},
            json={"input_text": "這是合成的契約驗證文字。"},
        )
        if response.status_code != 401:
            failures.append(
                "POST companion turn did not fail closed with 401: "
                f"returned {response.status_code}"
            )
            print(f"FAIL  POST companion turn fails closed: {response.status_code}")
        else:
            print("ok    POST companion turn fails closed with 401")
        check(
            "POST companion turn 401 body vs ErrorEnvelopeV1",
            response.json(),
            load("common/ErrorEnvelopeV1.json"),
        )

        protected_gets = sorted(
            path
            for path, item in OPENAPI["paths"].items()
            if "get" in item and path not in {"/health", "/ready"}
        )
        sample_uuid = "2a6f9c31-8e47-4b52-9d10-3c8a7e5b1a40"
        for path in protected_gets:
            url = re.sub(r"\{[^}]+\}", sample_uuid, path)
            params = (
                {"mode": "daycare"} if path == "/api/v1/me/authorized-elders" else None
            )
            response = await client.get(url, params=params)
            label = f"GET {path} fails closed"
            if response.status_code != 401:
                failures.append(
                    f"{label}: returned {response.status_code}, expected 401"
                )
                print(f"FAIL  {label}: {response.status_code}")
                continue
            check(
                f"{label} with ErrorEnvelopeV1",
                response.json(),
                load("common/ErrorEnvelopeV1.json"),
            )

    return len(failures)


if __name__ == "__main__":
    code = asyncio.run(main())
    print(
        "\nall live contract checks passed"
        if code == 0
        else f"\n{code} live contract failure(s)"
    )
    raise SystemExit(code)
