# kinsun.ai

智慧長照 AI 陪伴系統。設計文件在 [`docs/`](docs/)。

## Kiro 開發與架構設計

Repository 保留實際透過 Kiro 建立並執行的 Core API Foundation Spec，以及目前適用的
Steering 與 v1 Hooks：

- [`.kiro/specs/core-api-foundation/`](.kiro/specs/core-api-foundation/)：requirements、design、
  tasks 與 task execution metadata。
- [`.kiro/steering/`](.kiro/steering/)：產品、技術、結構、安全與人工確認規則。
- [`.kiro/hooks/`](.kiro/hooks/)：Spec traceability、測試、migration 與文件同步檢查。
- [`docs/kiro-development-evidence.md`](docs/kiro-development-evidence.md)：commit provenance、
  使用方式與證據邊界。

歷史 Spec 是開發過程證據，不取代目前的 `AGENTS.md`、產品文件、contracts 與 ADR。

## 本機開發環境

依 12 文件 §9.1，本機以 Docker Compose 提供資料層。目前已建立 PostgreSQL；Queue Stub 與 Object Storage Stub 之後再加。

### 需求

- Docker Desktop（含 Docker Compose v2）
- [uv](https://docs.astral.sh/uv/)（在本機跑 Alembic 用；只用 Docker 跑 migration 的話可略過）

### 啟動

```powershell
Copy-Item .env.example .env   # 第一次才需要，.env 不進版控
docker compose up -d postgres
docker compose ps
docker compose run --rm migrate   # 建立 eldercare_ai schema
```

`docker compose ps` 顯示 `healthy` 才算就緒。

### 連線資訊

| 項目 | 值 |
| --- | --- |
| Host / Port | `localhost:5432`（可用 `POSTGRES_PORT` 改） |
| Database | `kinsun`（測試用 `kinsun_test`） |
| User / Password | `kinsun` / `kinsun_local_dev` |
| 版本 | PostgreSQL 16（對齊 Aurora PostgreSQL Serverless v2） |

```
postgresql+psycopg://kinsun:kinsun_local_dev@localhost:5432/kinsun
```

本機 5432 已被占用時，改 `.env` 的 `POSTGRES_PORT`（例如 `15432`）再 `docker compose up -d postgres`。

### 常用指令

```powershell
docker compose exec postgres psql -U kinsun -d kinsun   # 進 psql
docker compose logs -f postgres                          # 看 log
docker compose stop postgres                             # 停止（保留資料）
docker compose down                                      # 移除容器（保留資料）
docker compose down -v                                   # 連資料一起清掉，下次重跑 init
```

Adminer（選用的 DB 管理介面，預設不啟動）：

```powershell
docker compose --profile tools up -d
# http://localhost:8080　System 選 PostgreSQL，Server 填 postgres
```

### Schema 從哪來

分成兩層，不要混：

- `docker/postgres/init/` 只建立 extension（`pgcrypto`、`citext`）與測試資料庫，**不建表**。
  只在資料 volume 是空的時候執行一次；改了內容要重跑，需先 `docker compose down -v`。
- **所有 table／index／constraint／trigger 由 Alembic 管理**，schema 名稱是 `eldercare_ai`。

## Core API

程式在 [`services/core-api/`](services/core-api/)：FastAPI ＋ SQLAlchemy 2.0 async，
目前涵蓋 Identity、Elder 授權、Consent、Voice Session metadata、Care Event、Memory、
Daily Summary、Family Report、Assignment、受控 Agent Tool、Deletion workflow，以及具
tenant 隔離與 replay protection 的 transactional outbox／consumer foundation。

```powershell
cd services/core-api
uv sync --extra test --extra dev
uv run pytest tests/unit          # 不需資料庫
uv run pytest tests/integration   # 需要 postgres 容器
uv run ruff check .
```

授權模型的重點：預設拒絕，每次請求都對 live DB 重新驗證，不做跨請求快取。
`BaseRepository` 強制每個查詢都帶 `tenant_id` 述詞，`tenant_id` 由 constructor 明確傳入
而非 contextvars——背景工作與 consumer 才能建立自己的可信 context。
查無此長者與無權限一律回同一個 404，避免探測長者是否存在。

ORM 的 Python 屬性統一是 `id`，實際對應各表自己的 PK 欄位（`actor.actor_id`、
`elder.elder_id`…），由每個 model 的 `__pk_name__` 宣告。新增 model 一定要設它。

## Agent Runtime

程式在 [`services/agent-runtime/`](services/agent-runtime/)：成員 C 的 Agent／RAG／Graph
範圍，目前是 M0 Foundation。

```powershell
cd services/agent-runtime
uv sync --extra test --extra dev
uv run pytest              # 不需資料庫、AWS 憑證或網路
uv run ruff check .
uvicorn --app-dir src agent_runtime.app:app --reload --port 8001
```

可執行的閉環：`POST /api/v1/agent/runs` → contract 驗證 → Orchestrator → Companion
Agent → Safety Evaluator → 回應。模型走 `MockModelProvider`，**不呼叫任何外部 LLM**，
也還沒接 Bedrock、OpenSearch 或 Neptune。

回應與 core-api 用同一組 envelope（`{"data", "meta"}` / `{"error"}`），
見 [ADR 0005](docs/adr/0005-agent-runtime-api-conventions.md)。

Safety Evaluator 目前是 deterministic 的關鍵字規則（停藥、改藥、診斷等），命中即 `BLOCK`
並改回安全訊息。**安全阻擋回的是 200 不是錯誤**——`data.result_status` 為 `BLOCKED`、
`data.reply_text` 換成安全訊息，長者仍然收到回覆。

範圍與邊界見 [`docs/ownership/member-c-scope.md`](docs/ownership/member-c-scope.md)，
架構見 [`docs/architecture/agent-runtime-overview.md`](docs/architecture/agent-runtime-overview.md)，
併入 monorepo 的決策見 [ADR 0004](docs/adr/0004-agent-runtime-into-monorepo.md)。

兩個服務各自維護 `pyproject.toml` 與 `uv.lock`，不共用虛擬環境。

## Frontend → Core → Agent 文字閉環

目前可執行的前端是 [`packages/frontend/`](packages/frontend/)。瀏覽器只呼叫
Next.js 的同源 `/backend/core/*`；BFF 從 `HttpOnly` Cookie 取得 Access Token，才在
伺服器端轉成 Core API 要求的 Bearer Header。瀏覽器 JavaScript 不讀取 Token，寫入
請求另有同源 Origin／CSRF gate。Core 會從可信認證 context 取得 actor／tenant，重新檢查 elder scope 與 `BASIC_VOICE` consent，建立
Voice Session，才以 server-to-server 方式呼叫 Agent Runtime `:8001`。Agent 的
安全結果由 Core 寫入稽核 metadata，再以統一 envelope 回給前端。

這一條目前是 **TEXT_ONLY fallback**。麥克風、ASR、WebSocket 與 TTS 尚未實作，
前端會明確顯示不可用，不會把文字輸入冒充成語音辨識結果。設定、啟動方式、
安全邊界與 E2E 證據見
[`docs/handover/2026-08-01-frontend-core-agent-integration.md`](docs/handover/2026-08-01-frontend-core-agent-integration.md)。

## API Contract

[`contracts/`](contracts/) 放 OpenAPI 3.1、AsyncAPI 3.0 與 JSON Schema。core-api 合約涵蓋
目前 runtime 的 44 個 operations；agent-runtime 另有 `/health` 與
`POST /api/v1/agent/runs` 的 executable OpenAPI。Handoff、Context Manifest、Safety
Evaluation 與 Tool schema 中仍有尚未接上 executable endpoint 的目標形狀，邊界見
[`contracts/README.md`](contracts/README.md) 與 [`contracts/DIVERGENCE.md`](contracts/DIVERGENCE.md)。

```powershell
uv run --with pyyaml --with jsonschema --with referencing python scripts/validate_contracts.py contracts
```

契約**以目前實作為準**，與文件 10 有實質差異（envelope 結構、錯誤欄位、狀態碼對應），
差異清單在 [`contracts/DIVERGENCE.md`](contracts/DIVERGENCE.md)，尚未決定往哪邊收斂。

## Database Migration（Alembic）

### 用 Docker 跑（不需要本機 Python）

```powershell
docker compose run --rm migrate                     # upgrade head
docker compose run --rm migrate alembic current     # 查目前版本
docker compose run --rm migrate alembic history     # 看歷史
```

### 用本機 uv 跑

```powershell
cd services/core-api
uv sync                       # 第一次
uv run alembic upgrade head
uv run alembic current
uv run alembic downgrade base # 砍掉整個 eldercare_ai schema
```

連線字串取自 `DATABASE_URL`，會自動從最近的 `.env` 讀。要指向測試庫：

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://kinsun:kinsun_local_dev@localhost:5432/kinsun_test"
```

`DATABASE_URL` 只維護一份，統一寫成 **asyncpg** 形式。應用層直接使用；
Alembic 走同步連線，`alembic/env.py` 會自行換成 psycopg。這是刻意保留兩個 driver
（見 [ADR 0003](docs/adr/0003-core-api-framework-and-schema-authority.md)）。

### 新增一個 migration

```powershell
cd services/core-api
uv run alembic revision -m "PROJ-123 add xxx table"
```

檔名格式為 `YYYYMMDD_HHMM_<slug>.py`（文件 13 §3.3）。

**`--autogenerate` 目前不能直接採用**：v0.1 baseline 來自手寫 SQL，48 張 baseline
table 中目前只有 33 張有 SQLAlchemy model；autogenerate 會把未映射的 table 誤判為
應刪除。新增 migration 時必須人工撰寫或逐項審查產物，不得套用自動產生的 drop。
原因與後續打算見 [ADR 0002](docs/adr/0002-alembic-baseline-strategy.md)。

### baseline 與 `docs/` 那份 SQL 的關係

[`docs/smart_eldercare_schema_v0_1.sql`](docs/smart_eldercare_schema_v0_1.sql) 是設計產出物，
也是匯入 DBeaver／DataGrip 看 ER 圖的來源。它的一份逐位元副本被凍結在
`services/core-api/alembic/versions/sql/` 底下，**那份才是實際套用到資料庫的權威版本**，
並且會在每次 upgrade 前驗證 SHA-256。

已套用的 migration 視為不可變。要改 schema 請新增 revision，不要動 baseline。

注意檔名叫 `smart_eldercare_schema_v0_1`，但它建立的 PostgreSQL schema 名稱是 `eldercare_ai`。
