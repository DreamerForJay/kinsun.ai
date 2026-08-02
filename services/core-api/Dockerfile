# Migration Job image（文件 13 §七）。
# 這不是 Core API 的應用程式映像；FastAPI 已由 ADR 0003 定案，但本 image 只安裝並
# 執行 Alembic migration 所需的 Core dependency lock 與程式碼。
FROM python:3.12-slim-bookworm

LABEL io.kinsun.artifact="core-migration"

# 版本鎖死，避免 CI 某天突然換到不同的 uv 行為
COPY --from=ghcr.io/astral-sh/uv:0.11.25 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    HOME=/tmp \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /app \
        --shell /usr/sbin/nologin app

WORKDIR /app

# 依賴層獨立：只改 migration 內容時不需要重裝套件
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY --chown=10001:10001 alembic.ini ./
COPY --chown=10001:10001 alembic ./alembic
# app/ 是必要的：alembic/env.py 匯入 app.models 取得 target_metadata
COPY --chown=10001:10001 app ./app

# 文件 13 §七：Migration Job 與 Core API 使用相同 Dependency Lock，指令獨立
USER 10001:10001

ENTRYPOINT ["python", "-m", "app.container_entrypoint", "postgresql+psycopg"]
CMD ["python", "-m", "app.migration_job"]
