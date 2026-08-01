# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim-bookworm AS dependencies

# Keep the dependency installer deterministic and out of the runtime image.
COPY --from=ghcr.io/astral-sh/uv:0.11.25 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /build

# Dependency metadata is copied before application code to preserve the cache.
COPY services/agent-runtime/pyproject.toml services/agent-runtime/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project


FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

LABEL io.kinsun.artifact="agent-runtime"

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH=/app/services/agent-runtime/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    LOG_LEVEL=INFO \
    MODEL_PROVIDER=mock \
    RAG_MODE=disabled

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid 10001 \
        --home-dir /home/app --create-home --shell /usr/sbin/nologin app

# Preserve the repository-relative source depth used by the settings resolver.
WORKDIR /app/services/agent-runtime

COPY --from=dependencies --chown=10001:10001 /opt/venv /opt/venv
COPY --chown=10001:10001 services/agent-runtime/src ./src
COPY --chown=10001:10001 \
    config/rag/embedding.yaml \
    config/rag/opensearch-index-v1.json \
    config/rag/hybrid-natural-language.json \
    config/rag/hybrid-legal.json \
    /app/config/rag/

USER 10001:10001

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-m", "agent_runtime.healthcheck"]

ENTRYPOINT ["uvicorn"]
CMD ["agent_runtime.app:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1", "--no-access-log", "--no-server-header"]
