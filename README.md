# kinsun.ai

<p align="center">
  <img src="packages/frontend/public/mascot.png" alt="小暖" width="220" />
</p>

<p align="center"><i>「小暖陪你聊生活，也陪你安心過每一天。」</i></p>

智慧長照 AI 陪伴系統。設計文件在 [`docs/`](docs/)。

## 開發理念

- **人機協作，不取代照護**：AI 負責陪伴、記錄與整理，最終判斷與照護行動仍由家屬、
  照服員與專業人員決定；系統不提供醫療診斷或治療建議。
- **AI 生成內容先是候選，經確認才算數**：對話擷取的照護事件、長者記憶與每日摘要一律
  先是候選／草稿，須經長者本人確認或人工覆核才成為正式紀錄；家屬只看得到已發布的報表。
- **預設拒絕，每次請求重新驗證**：Core 對每個請求重新檢查身分、租戶、長者授權與同意，
  不做跨請求快取；查無資源與無權限一律回同一個 404，避免探測他人資料是否存在。
- **Fail closed，不假裝成功**：AWS 憑證、模型 provider、RAG Allowlist 簽署或
  LINE／Speech Gateway 設定不完整時，系統回報明確錯誤或 fallback，不會靜默生成內容
  冒充已完成。
- **展示資料一律合成**：Demo 與測試只使用模擬或去識別化資料，不使用真實長者個資。

## 核心功能

對應競賽命題必做模組，以下為目前實際可執行的狀態：

| 模組 | 內容 | 狀態 |
| --- | --- | --- |
| Module A．語音互動陪伴 | 國語／英語語音辨識與合成（Amazon Transcribe／Polly）；台語／客語語音辨識（自建 SageMaker ASR）。陪伴對話由 Agent Runtime 生成，Safety Evaluator 攔截停藥、改藥、診斷等高風險內容並改回安全訊息 | 可執行；台語／客語目前只有辨識、尚無語音合成，回覆會顯示文字 |
| Module B．生活記錄與智慧摘要 | 照護事件與長者記憶皆先成為候選，經長者確認或人工覆核才成為正式紀錄；每日摘要以 Draft／Review／Published 狀態機管理，內容可追溯回原始事件 ID | 狀態機與 API 可執行 |
| Module C．照護者資訊介面 | 照護者後台（`/dashboard`）顯示長者列表、長者詳情、AI 每日摘要與互動統計；家屬報表（`/family`）僅顯示已發布內容 | 可執行 |
| 家屬推播通知（選做） | LINE 官方帳號每日 08:00（Asia/Taipei）推播已發布家屬報表的更新提示，不含長者姓名或報表內容 | 程式與 contract 已實作，外部排程尚未部署（見「LINE 整合」） |
| 知識庫（選做） | RAG 檢索：一般資訊／法規類問題會附上 3–5 筆完整引用來源，查無資料時明確回報，不由模型猜測 | staging-only，需簽署 Allowlist 才可用於 production |

## 小暖｜陪伴角色

小暖是外型約 10–12 歲的中性 AI 數位孫輩，胸前佩戴的小葉子徽章象徵長者每天累積的
生活記憶與健康習慣。產品內的 `CompanionCharacter` 元件（見
[`packages/frontend/src/components/voice/CompanionCharacter.tsx`](packages/frontend/src/components/voice/CompanionCharacter.tsx)）
依對話狀態切換對應的動態影片，靜止狀態則回退到上方靜態圖：

| idle 待機 | listening 聆聽 | processing 思考 | speaking 回應 | sleeping 休息 |
| :---: | :---: | :---: | :---: | :---: |
| <video src="packages/frontend/public/video/happy.mp4" width="160" controls></video> | <video src="packages/frontend/public/video/listen.mp4" width="160" controls></video> | <video src="packages/frontend/public/video/remind.mp4" width="160" controls></video> | <video src="packages/frontend/public/video/encourage.mp4" width="160" controls></video> | <video src="packages/frontend/public/video/comfort.mp4" width="160" controls></video> |

角色設計探索過程見 [`pic/`](pic/)；`prefers-reduced-motion` 使用者會看到影片第一幀
而非播放中的動畫，資訊不因此遺失。

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
範圍，目前是 M0 Agent Foundation，加上第一版 staging-only RAG Retrieval。

```powershell
cd services/agent-runtime
uv sync --extra test --extra dev
uv run pytest              # 不需資料庫、AWS 憑證或網路
uv run ruff check .
uvicorn --app-dir src agent_runtime.app:app --reload --port 8001
```

Agent 閉環：`POST /api/v1/agent/runs` → contract 驗證 → Orchestrator → Companion
Agent → Safety Evaluator → 回應；模型仍走 `MockModelProvider`。另有
`POST /api/v1/rag/retrievals` 的 Bedrock query embedding／OpenSearch Hybrid Search adapter；
`general_information`／`legal_reference` Agent Run 會把 3～5 個完整引用 chunk 放入
Context Manifest，查無資料時不呼叫模型猜測，沒有 provider 設定時回明確 fallback。

RAG Allowlist 目前尚未正式簽署、Human Review 未完成，只能在 staging 明確設定
`RAG_REQUIRE_OWNER_SIGNATURE=false` 時使用 unsigned development override，且雜湊與內容
驗證仍是不可略過的 hard gate；production 需要正式簽署並開啟 `RAG_PRODUCTION_ENABLED=true`。
目前沒有可用的 AWS staging 連線，尚未建立或驗證真實 OpenSearch index。

回應與 core-api 用同一組 envelope（`{"data", "meta"}` / `{"error"}`），
見 [ADR 0005](docs/adr/0005-agent-runtime-api-conventions.md)。

Safety Evaluator 目前是 deterministic 的關鍵字規則（停藥、改藥、診斷等），命中即 `BLOCK`
並改回安全訊息。**安全阻擋回的是 200 不是錯誤**——`data.result_status` 為 `BLOCKED`、
`data.reply_text` 換成安全訊息，長者仍然收到回覆。

範圍與邊界見 [`docs/ownership/member-c-scope.md`](docs/ownership/member-c-scope.md)，
架構見 [`docs/architecture/agent-runtime-overview.md`](docs/architecture/agent-runtime-overview.md)，
併入 monorepo 的決策見 [ADR 0004](docs/adr/0004-agent-runtime-into-monorepo.md)。

兩個服務各自維護 `pyproject.toml` 與 `uv.lock`，不共用虛擬環境。

## Frontend

程式在 [`packages/frontend/`](packages/frontend/)：Next.js 16（Turbopack）＋ React 19 的
multi-role PWA，同時服務長者、家屬與照服員三種身分，並兼任 Cognito／Core API 的 BFF。
版本與升級理由見 [ADR 0006](docs/adr/0006-frontend-stack-and-app-topology.md)、
[ADR 0008](docs/adr/0008-next-16-supported-release-upgrade.md)。

```powershell
cd packages/frontend
npm install         # 於 repo 根目錄執行即可（workspaces）
npm run dev         # http://localhost:3000
npm run typecheck   # next typegen && tsc --noEmit
npm run build
npm test
```

未登入時看到的是公開 landing page（`/`，含產品介紹、隱私權政策、服務條款、資料權利、
無障礙聲明），介面文字支援中文（zh-Hant）／英文切換。登入後依角色分流到
`/`（長者陪伴對話）、`/dashboard`（照服員／照護者後台）、`/family`（家屬報表）。

登入支援 Google 與 LINE Login 兩種 Cognito federated provider（`LINE_LOGIN_ENABLED`
關閉時 UI 不顯示 LINE 選項，安全門檻在伺服器端強制執行，不只是隱藏按鈕）。瀏覽器只呼叫
Next.js 的同源 `/backend/*`；BFF 從 `HttpOnly` Cookie 取得 Access Token，才在伺服器端轉成
Core API 要求的 Bearer Header，瀏覽器 JavaScript 不讀取 Token，寫入請求另有同源
Origin／CSRF gate。

長者的陪伴對話走 Core 的**文字**單輪 companion-turn（`transport_status = TEXT_ONLY`）：
Core 從可信認證 context 取得 actor／tenant，重新檢查 elder scope 與 `BASIC_VOICE`
consent、建立 Voice Session，才以 server-to-server 方式呼叫 Agent Runtime `:8001`；
Agent 的安全結果由 Core 寫入稽核 metadata，再以統一 envelope 回給前端。語音輸入輸出
另見下方「語音（Speech Gateway）」——兩者是分開的關注點：Core 決定「可不可以說、
說了什麼算數」，Speech Gateway 只負責音訊轉文字／文字轉音訊，本身不留狀態。

設定、啟動方式、安全邊界與 E2E 證據見
[`docs/handover/2026-08-01-frontend-core-agent-integration.md`](docs/handover/2026-08-01-frontend-core-agent-integration.md)
（文字閉環部分仍準確；語音已如下方所述進一步接上 Speech Gateway）。

## 語音（Speech Gateway）

程式在 [`services/speech-gateway/`](services/speech-gateway/)：獨立的 FastAPI 服務，
只做「音訊轉文字、文字轉音訊」，不儲存逐字稿、不判斷 consent、不擷取事件——這些一律
留給 Core。國語／英語辨識走 Amazon Transcribe，台語／客語辨識走自建 SageMaker ASR
endpoint；語音合成走 Amazon Polly，目前尚未部署台語／客語的 TTS endpoint，因此那兩種
語言的回覆只顯示文字，不會播放語音（前端會明確說明，不會假裝播放失敗）。

```powershell
cd services/speech-gateway
uv sync --extra test --extra dev
uv run pytest
uvicorn speech_gateway.app:app --reload --port 8002
```

這條路徑是**逐輪呼叫**，不是即時串流 WebSocket：瀏覽器錄一段音訊、上傳給 Speech
Gateway 轉文字、把確認後的文字送進 Core 的文字 companion-turn、拿到回覆文字再送回
Speech Gateway 合成語音。沒有設定 AWS 憑證／SageMaker endpoint 時會 fail closed
（回傳明確錯誤，不是靜默假成功）。前端串接與語言路由邏輯見
`packages/frontend/src/lib/voice/canonical-voice-turn.ts`。

## LINE 整合

專案裡有兩套彼此獨立、不可互相比較 subject 的 LINE 身分：

- **LINE Login**：Cognito federated OAuth provider，用來登入既有帳號（需先以 Google
  登入過並完成連結），走 `/account/sign-in-methods` 與 `/backend/auth/identities/line/*`。
- **LINE 官方帳號 Account Linking**：長者／家屬把 Core Actor 與 LINE Messaging API
  的 `external_identity` 綁定，用於每日家屬報表推播（`POST
  /api/v1/internal/notification-jobs/line-daily`，08:00 Asia/Taipei，只推播已 `PUBLISHED`
  的正式報表，不含長者姓名或報表內容），走 `/line/account-link` 與
  `/backend/line/account-link/*`。

兩者都是 **feature-gated、尚未有 staging 部署證據**的程式／synth 層實作（對應的
Cognito domain、Secrets Manager 值、固定 HTTPS origin、外部 Scheduler 均待補），
完整威脅模型、加密邊界與尚未完成事項見 [`contracts/DIVERGENCE.md`](contracts/DIVERGENCE.md)。
排程呼叫的介面說明見
[`services/notification-worker/README.md`](services/notification-worker/README.md)。
知識庫的 ingestion pipeline（Bedrock Cohere Embed v4 → OpenSearch）在
[`services/rag-ingestion/`](services/rag-ingestion/)，離線、staging-only，已有可執行程式與測試。

## API Contract

[`contracts/`](contracts/) 放 OpenAPI 3.1、AsyncAPI 3.0 與 JSON Schema。core-api 合約涵蓋
目前 runtime 的 57 個 operations（含 Voice Ticket、LINE Login federation、LINE Account
Linking 與每日通知 job）；agent-runtime 另有 `/health`、`POST /api/v1/agent/runs` 與
`POST /api/v1/rag/retrievals` 的 executable OpenAPI。Handoff、Context Manifest、Safety
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
