import json

from agent_runtime import healthcheck


class StubResponse:
    def __init__(self, *, status: int, payload: object) -> None:
        self.status = status
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None

    def read(self, limit: int) -> bytes:
        return self._body[:limit]


def test_healthcheck_accepts_only_expected_service_contract(monkeypatch) -> None:
    def open_ok(request, *, timeout):
        assert request.full_url == "http://127.0.0.1:8001/health"
        assert timeout == 2.0
        return StubResponse(
            status=200,
            payload={"status": "ok", "service": "agent-runtime", "version": "1.0.0"},
        )

    monkeypatch.setattr(healthcheck, "urlopen", open_ok)

    assert healthcheck.is_healthy()
    assert healthcheck.main() == 0


def test_healthcheck_fails_closed_for_wrong_service(monkeypatch) -> None:
    monkeypatch.setattr(
        healthcheck,
        "urlopen",
        lambda request, *, timeout: StubResponse(
            status=200,
            payload={"status": "ok", "service": "different-service"},
        ),
    )

    assert healthcheck.is_healthy() is False
    assert healthcheck.main() == 1


def test_healthcheck_fails_closed_when_runtime_is_unreachable(monkeypatch) -> None:
    def raise_connection_error(request, *, timeout):
        raise OSError("synthetic connection failure")

    monkeypatch.setattr(healthcheck, "urlopen", raise_connection_error)

    assert healthcheck.is_healthy() is False
