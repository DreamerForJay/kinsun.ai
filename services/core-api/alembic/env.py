"""Alembic environment for the Aurora PostgreSQL system of record.

設計重點：
- 連線字串一律由 DATABASE_URL 環境變數提供，不寫進 alembic.ini（AGENTS.md §9：.env 不進版控）。
- alembic_version 放在 public schema，業務物件放在 eldercare_ai schema。
  baseline 的 downgrade 會 DROP SCHEMA eldercare_ai CASCADE，版本表若放在同一個
  schema 會被一起刪掉，Alembic 就再也不知道自己在哪個版本。
- target_metadata 指向 app.db.base.Base.metadata。models 只涵蓋 48 張表中的 9 張，
  因此 `--autogenerate` 會把其餘 39 張誤判為「應該刪除」。在 models 補齊之前，
  autogenerate 產生的 migration 一律需人工檢查後才可使用（見 docs/adr/0002）。
"""

from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# 業務物件所在的 PostgreSQL schema（見 docs/smart_eldercare_schema_v0_1.sql）
TARGET_SCHEMA = "eldercare_ai"

# Alembic 版本表刻意留在 public，讓 baseline 可以安全地整個 drop 掉 TARGET_SCHEMA
VERSION_TABLE_SCHEMA = "public"

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 匯入 app.models 讓所有 model 註冊進 metadata。
# 必須放在 fileConfig() 之後，因此不在檔案頂端。
from app import models  # noqa: E402,F401
from app.db.base import Base  # noqa: E402

target_metadata = Base.metadata


def _load_dotenv() -> None:
    """把最近的 .env 讀進 os.environ，已存在的環境變數優先。

    只做最小解析（KEY=VALUE、# 註解、可選引號），避免為了本機方便多壓一個依賴。
    在容器裡跑時通常沒有 .env，直接吃 compose 傳進來的環境變數。
    """
    here = Path(__file__).resolve()
    # 從 alembic/ 往上找最近的 .env：本機會命中 services/core-api/.env 或 repo 根目錄的
    # .env。切片而非索引，容器裡路徑只有 /app/alembic 這麼淺也不會炸；上限 4 層避免
    # 誤抓到 repo 之外的 .env。
    for directory in here.parents[:4]:
        env_file = directory / ".env"
        if not env_file.is_file():
            continue
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)
        break


def get_database_url() -> str:
    """DATABASE_URL，正規化成 Alembic 用的同步 psycopg driver。

    專案只有一個 DATABASE_URL，而應用層與 migration 用不同 driver：
    FastAPI 走非同步的 asyncpg，Alembic 走同步的 psycopg。這裡把 asyncpg 的
    scheme 換掉，讓同一份 .env 兩邊都能用，不必維護兩個變數。
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        _load_dotenv()
        url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL 未設定。請複製 .env.example 成 .env，或直接匯出環境變數，例如：\n"
            "  $env:DATABASE_URL = 'postgresql+asyncpg://kinsun:kinsun_local_dev@localhost:5432/kinsun'"
        )
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg://")


def run_migrations_offline() -> None:
    """產生 SQL 腳本而不連線資料庫（`alembic upgrade head --sql`）。

    文件 13 §六要求 Staging Dry Run 前能先產出可審查的 SQL。
    """
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        version_table_schema=VERSION_TABLE_SCHEMA,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table_schema=VERSION_TABLE_SCHEMA,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
