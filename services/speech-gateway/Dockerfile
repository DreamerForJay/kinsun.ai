# syntax=docker/dockerfile:1.7
#
# Mirrors services/agent-runtime/Dockerfile so both canonical Python services
# build, run and are validated the same way (linux/amd64, non-root uid 10001,
# uv-locked dependencies, artifact label for ECR release validation).

ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim-bookworm AS dependencies

COPY --from=ghcr.io/astral-sh/uv:0.11.25 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /build

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project


FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

LABEL io.kinsun.artifact="speech-gateway"

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    LOG_LEVEL=INFO

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid 10001 \
        --home-dir /home/app --create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=dependencies --chown=10001:10001 /opt/venv /opt/venv
COPY --chown=10001:10001 src ./src

USER 10001:10001

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8002/health', timeout=2).status == 200 else 1)"]

ENTRYPOINT ["uvicorn"]
CMD ["speech_gateway.app:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "1", "--no-access-log", "--no-server-header"]
