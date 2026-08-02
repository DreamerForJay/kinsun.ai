from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[2]


def test_docker_context_is_an_explicit_allowlist() -> None:
    entries = {
        line.strip()
        for line in (SERVICE_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert entries == {
        "*",
        "!Dockerfile",
        "!.dockerignore",
        "!pyproject.toml",
        "!uv.lock",
        "!src/",
        "!src/**",
    }

    root_context_entries = {
        line.strip()
        for line in (SERVICE_ROOT / "Dockerfile.dockerignore")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert root_context_entries == {
        "**",
        "!services/",
        "!services/agent-runtime/",
        "!services/agent-runtime/pyproject.toml",
        "!services/agent-runtime/uv.lock",
        "!services/agent-runtime/src/",
        "!services/agent-runtime/src/**",
        "!config/",
        "!config/rag/",
        "!config/rag/embedding.yaml",
        "!config/rag/opensearch-index-v1.json",
        "!config/rag/hybrid-natural-language.json",
        "!config/rag/hybrid-legal.json",
    }


def test_runtime_image_is_non_root_and_safe_by_default() -> None:
    dockerfile = (SERVICE_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM python:${PYTHON_VERSION}-slim-bookworm AS dependencies" in dockerfile
    assert "FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime" in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert dockerfile.index("USER 10001:10001") < dockerfile.index("ENTRYPOINT")
    assert "MODEL_PROVIDER=mock" in dockerfile
    assert "RAG_MODE=disabled" in dockerfile
    assert 'CMD ["python", "-m", "agent_runtime.healthcheck"]' in dockerfile
    assert "COPY . " not in dockerfile
    assert "data/rag" not in dockerfile
    for config_name in (
        "embedding.yaml",
        "opensearch-index-v1.json",
        "hybrid-natural-language.json",
        "hybrid-legal.json",
    ):
        assert f"config/rag/{config_name}" in dockerfile
