"""Dependency-free container health probe.

The probe deliberately checks only process readiness. It does not call Bedrock,
OpenSearch, Core API, or any endpoint that could include elder data.
"""

from __future__ import annotations

import json
from urllib.request import Request, urlopen

HEALTH_URL = "http://127.0.0.1:8001/health"
MAX_RESPONSE_BYTES = 4096


def is_healthy(*, timeout_seconds: float = 2.0) -> bool:
    """Return whether the local runtime exposes the expected health contract."""

    request = Request(HEALTH_URL, headers={"User-Agent": "kinsun-agent-runtime-healthcheck"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            if response.status != 200:
                return False
            payload = json.loads(response.read(MAX_RESPONSE_BYTES))
    except (OSError, TimeoutError, ValueError, json.JSONDecodeError):
        return False

    return payload.get("status") == "ok" and payload.get("service") == "agent-runtime"


def main() -> int:
    """Use a conventional process exit code for Docker and ECS health checks."""

    return 0 if is_healthy() else 1


if __name__ == "__main__":
    raise SystemExit(main())
