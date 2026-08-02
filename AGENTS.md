# AGENTS.md

本文件適用於整個 `kinsun.ai` repository。所有代理在分析、設計、實作、測試與文件更新時，都必須遵守本文件及 `docs/` 中的產品規格。

## 1. 專案狀態

- 本專案是 AWS Hackathon 的 Voice-first 智慧長照 AI 陪伴系統。
- 目前 repository 具備文件 12 定義的 Monorepo 目錄骨架、本機 PostgreSQL／Docker Compose 基礎設施，
  以及以下有程式碼的單元：
  - `services/core-api`：第一個垂直切片——Identity、Elder 授權 policy、tenant 隔離的
    repository 層與 transactional outbox。
  - `services/agent-runtime`：M0 Foundation——contract 驗證、單輪 Orchestrator、
    Companion Agent、deterministic Safety Evaluator；主要回答仍走 Mock Provider，
    staging-only RAG adapter 可呼叫 Bedrock embedding／OpenSearch，但不接 Neptune，
    不得描述成 production runtime（[ADR 0004](docs/adr/0004-agent-runtime-into-monorepo.md)）。
  - `services/rag-ingestion`：RAG 文件 ingestion 與 allowlist 建置。搭配
    agent-runtime 的 **staging-only** RAG 路徑，尚未對真實 AWS／OpenSearch 環境驗證，
    不得描述成可用於 production（見 `services/agent-runtime/AGENTS.md`）。
  - `packages/frontend`：**唯一的前端**，單一 multi-role PWA，Next.js 16 App Router + React 19，
    同時是 BFF（Cognito OAuth 與 access token 留在伺服器端，反向代理 core-api）
    （[ADR 0006](docs/adr/0006-frontend-stack-and-app-topology.md)）。
    `apps/` 已依 ADR 0006 清空，不要把 `elder-web`／`care-web`／`family-web` 加回來。
  - `packages/shared`：前端與 legacy backend 共用的 TypeScript 型別；不是 Domain authority，
    跨服務形狀以 `contracts/` 為準。
  其餘服務目錄（`speech-gateway`、`projection-worker`、`notification-worker`、
  `report-worker`）仍是空殼。
- **`packages/backend` 與現有 `infrastructure/lib/elderly-care-stack.ts` 已由
  [ADR 0007](docs/adr/0007-canonical-backend-and-aws-deployment-authority.md) 定為 legacy**：
  不加入新功能，也不得部署現有 Lambda／DynamoDB／另一套 Cognito stack。一般 HTTP 主線
  只走 Next.js BFF → Python Core → Agent Runtime；`NEXT_PUBLIC_WS_URL` 的舊語音路徑僅是
  預設關閉、限期至 2026-08-16 的 synthetic staging/demo 例外，不得進 production。
  AWS CDK v2 已定為 canonical IaC 工具；`kinsun-staging-foundation-v1` 已建立 VPC、ECS
  cluster、ECR、Aurora、Secrets、Logs 與 IAM foundation。四個 runtime／migration image 與
  `kinsun-staging-application-v1` template 已可在本機建立／驗證，但 AWS 尚未建立 canonical
  ECS application task／service，不能描述成 application runtime 已上線。Frontend 已依
  [ADR 0008](docs/adr/0008-next-16-supported-release-upgrade.md) 升至受支援 release，且本機
  production audit／Linux image smoke 已通過；這只解除 framework dependency blocker，
  不代表 ECR push、Cognito callback、application deploy 或公開流量 gate 已完成。
- 尚未建立 CI quality gate。
- 不得把 Target Architecture、建議目錄或候選服務描述成已實作功能。
- 開始實作前，先確認工作項目對應的 Persona、User Story、Acceptance Criteria、Domain State、Security Gate 與 Test Gate。

## 2. 規格來源與優先順序

需求解讀依下列順序：

1. `docs/01智慧長照 AI 陪伴系統－產品方向與範圍基準 v1.2.docx`：產品範圍、成功條件與非目標。
2. `docs/01A智慧長照 AI 陪伴系統－使用者研究與 Demo Persona v0.2.docx`：Persona、情境與證據邊界。
3. `docs/02智慧長照 AI 陪伴系統－使用者故事與驗收條件 v1.3.2.docx`：User Story 與 Acceptance Criteria。
4. `docs/03智慧長照 AI 陪伴系統－Story Map v1.2.xlsx`：Wave、Gate、Backlog 狀態與 Demo Traceability。
5. `docs/06`、`07`、`10`、`11`：Domain、Security、Contract 與 Test 規格。
6. 其他 `docs/` 文件：UX、Workflow、AWS、Agent、交付、維運、評估與退場規則。

若文件互相衝突：

- 不要自行挑選最方便的版本。
- 優先採取較安全、較不會洩漏資料、較可回復的行為。
- 在 PR／變更說明中列出衝突、採用的暫定解讀與需要 Owner 決策的項目。
- 目前已知需要收斂：01／02 與 07／11 的延遲門檻不完全一致；Story Map 總覽可能有 Wave 標籤重複。

## 3. 核心交付順序

第一條 Gate 1 Vertical Slice 是主要實作脊柱：

1. 林阿嬤明確同意後開始語音互動。
2. ASR 對低信心內容要求簡短確認，不假裝辨識成功。
3. Orchestrator 產生安全、簡短且符合語言偏好的回覆。
4. Event／Memory 只能先成為 Candidate。
5. 長期記憶必須由長者明確確認；照護事件依規格完成人工覆核。
6. 正式狀態寫入 Aurora，並透過 Transactional Outbox 發布。
7. Neptune／OpenSearch 完成可追蹤、可重建的 Projection。
8. 後續對話只能重用已確認、未撤回且仍在有效 Scope 內的資料。
9. 產生有來源連結的 Daily Summary，供照服員覆核。
10. 保存 Demo、Trace、Contract、Safety 與 Failure-path 證據。

Wave 順序：

- Wave 1：Voice、Event、Confirmed Memory、Graph reuse。
- Wave 2：照服員摘要、覆核與待辦。
- Wave 3：RAG、Care Signal、家屬報表／通知、受控主動陪伴、English。
- Wave 4：遊戲、Gamification、低資源語言與進階 ASR。

除非使用者明確改變優先順序，不要為後期功能犧牲 Gate 1 的可演示閉環。

## 4. 不可違反的產品與安全邊界

- 不提供診斷、治療建議或取代專業照護決策。
- 不把模型輸出、推論、缺少資料或失敗結果描述成已確認事實。
- 未確認的 Memory Candidate 不得進長期記憶、Graph、報表或後續對話事實。
- 未覆核的 Event Candidate 不得成為 Verified Event。
- Draft Family Report 不得被家屬或通知預覽取得。
- Family App／Web 的 `PUBLISHED` Report 是正式內容來源；LINE／Email 只能做最小通知與安全連結。
- 長者的「不要記」、「不要再提」、「停止」與 Consent Revocation 必須立即優先於 Retry、Replay、Backfill、Scheduler 與主動陪伴。
- 不使用恐懼、內疚、壓力、欺騙或情緒依賴設計提高互動率。
- Demo、測試、Eval 與截圖只能使用 Synthetic 或完成去識別的資料。

零容忍結果：

- Cross-elder 或 Cross-tenant 資料暴露。
- 未授權讀寫、Tool 執行或 Consent bypass。
- Secret、Token、完整 Prompt、完整 Transcript／Audio 出現在一般 Log。
- 醫療危險建議。
- 未確認記憶被當成事實。
- 已刪除或已撤回資料因 Replay／Projection rebuild 再次出現。
- Draft Report、錯誤收件或超出 Family Share Scope 的內容外洩。

## 5. Authorization、Consent 與資料範圍

- 採 RBAC + ABAC，並預設拒絕。
- 每次正式讀取、寫入及 Agent Tool Command 都由 Core 重新驗證：
  - `tenant_id`
  - `elder_id`
  - `care_unit_id`
  - relationship／family share scope
  - assignment
  - consent purpose／version
  - actor role
  - resource state
  - time／purpose
- 不信任 Client 或模型傳入的 Actor、Tenant、Elder、Assignment 或 Permission Scope。
- Consent Purpose 必須分離，不得以單一總開關代替：
  - `BASIC_VOICE`
  - `TRANSCRIPT_STORAGE`
  - `CARE_EVENT_EXTRACTION`
  - `LONG_TERM_MEMORY`
  - `COMPANION_SIGNAL_ANALYSIS`
  - `PROACTIVE_COMPANION`
  - `FAMILY_SHARING`
- Consent 撤回後先停止未來處理，再依 Retention／Deletion Workflow 處置資料。

## 6. 架構不變量

- Aurora PostgreSQL／Domain Core 是正式交易資料與狀態的 Source of Truth。
- Neptune、OpenSearch、Cache 與 Agent Memory 是 Projection 或 Working State，必須可由正式資料重建。
- 不從 Graph、Search 或模型輸出反推正式授權或正式狀態。
- 正式寫入使用 Transactional Outbox；採 Outbox → EventBridge → 每個 Consumer 專屬 SQS／DLQ。
- 不使用 Database + Graph／Index／Event Bus 的無保護 Dual Write。
- 非同步 Consumer 必須 Idempotent、可重試、可觀測，並在處理前重新檢查撤回、刪除與 Scope。
- 長流程／人工流程使用顯式 State Machine；不得以隱含 Prompt 狀態代替 Domain State。
- 正式刪除使用 Tombstone 防止 DLQ Replay、Backfill、Graph rebuild、Index rebuild 或 Backup restore 復活資料。

Target AWS Architecture 目前包含：

- Single multi-role PWA。
- Python modular monolith on ECS/Fargate。
- API Gateway HTTP／WebSocket、Cognito。
- Bedrock AgentCore Runtime、Bedrock Models／Guardrails。
- Aurora PostgreSQL、Neptune Serverless、OpenSearch Serverless、S3。
- EventBridge、SQS／DLQ、Step Functions、Scheduler。
- SES／LINE Notification Adapter。

以上是目標規劃，不代表服務已建立。

## 7. Agent 與 AI 實作規則

- 採受控 Orchestrator，不建立 Agent Debate、無限遞迴或自由互相呼叫。
- 同步流程上限依 Agent 規格：最多 3 次模型決策、2 輪 Tool、5 次 Tool Call，以及 1 次 Rewrite／Context rebuild；若規格更新則依新版本執行。
- Agent 只能呼叫 Allowlist 中且有版本的 Tool。
- 高風險 Tool 即使由 Agent 選擇，也必須由 Python Core 重新執行 Authorization、Consent、State 與 Idempotency 檢查。
- Context 依層次組合：Policy → Auth → Consent → Current turn → Session → Active confirmed memory → Verified care data → Graph → RAG → Tool results → Output constraints。
- 每次重要 Agent 執行需能追溯實際的 Agent、Prompt、Model route、Policy、Guardrail、Tool schema、Context manifest 與 Release Version。
- RAG 必須保存來源、版本、有效日期、覆核狀態與 Metadata Filter；沒有可靠來源時明確回覆資料不足。
- LLM-as-Judge 不得覆蓋 Deterministic Security／Schema／Permission Gate。

## 8. API、Event 與版本規則

- REST 使用 `/api/v1/...` Major Path Version。
- WebSocket 只傳輸 Voice Session State 與已定義事件，不暴露內部 Prompt、Agent Trace、Secret 或其他長者 Context。
- OpenAPI 3.1、AsyncAPI 與 JSON Schema 是機器可驗證 Contract，放在 `contracts/`。細節見 §8.1、§8.2。
- API、Domain Event、Agent Handoff、Tool、Candidate、Report 與 Export 都需要 Schema Validation。
- 正式 Event 發布後視為不可變歷史契約；破壞性變更建立新 `event_version`。
- Consumer 先支援新舊版本，Producer 才切換。
- Database 變更採 Expand → Migrate → Contract。
- 使用 Idempotency Key、Optimistic Concurrency、Correlation／Causation ID 與明確 Error Code。
- 不可只記錄 `latest`；需保存實際使用的 API、Event、Schema、Agent、Prompt、Model、Policy、Speech、RAG、Graph、Export 與 Release Version。

## 8.1 Contract 規格

### 目前狀態

`contracts/` **以目前實作為準，不是以文件 10 為準**。兩者在 envelope 結構、錯誤欄位與
狀態碼對應上有實質差異，全部列在 [`contracts/DIVERGENCE.md`](contracts/DIVERGENCE.md)，
尚未決定收斂方向。**改動 contract 或 API 之前先讀那份清單**，不要以為文件 10 就是現況。

若你的變更消除或新增了一項差異，同步更新 `DIVERGENCE.md`。

### 目錄與檔名

```
contracts/
├── openapi/<service>.v<major>.yaml   REST，一個服務一份
├── asyncapi/<service>.v<major>.yaml  Domain Event（尚未建立）
├── schemas/
│   ├── common/    跨領域共用：envelope、分頁、錯誤
│   ├── domain/    業務 DTO
│   ├── events/    Domain Event payload（尚未建立）
│   ├── tools/     Agent Tool request／result
│   └── agent/     Agent Run、Handoff、Context Manifest、Safety Evaluation
└── examples/{valid,invalid}/
```

### 命名

- Schema 檔名與 `title` 為 PascalCase＋版本：`ElderSummaryV1.json`（文件 10 §3.1）。
- `$id` 用絕對 URI：`https://kinsun.ai/contracts/schemas/<dir>/<Name>.json`。
  跨檔 `$ref` 一律指 `$id`，不要用相對路徑，否則換工具就解不開。
- JSON 欄位 snake_case；REST 路徑複數名詞、kebab-case；時間 ISO 8601 UTC。
- ID 一律 UUID，不得暴露遞增流水號。

### 硬性規則

- **`additionalProperties: false`**。契約要能擋下多餘欄位，否則洩漏了也測不出來。
- **enum 必須與 `eldercare_ai` schema 一致**（PG ENUM 的 label 或 CHECK 的允許值）。
  contract 比資料庫寬鬆，錯誤會延到 INSERT 才爆；比資料庫嚴格則是合法的收斂。
- **分頁只能用 opaque cursor**，不得出現 `offset`、`page_number` 或 `total`。
  可猜測的 offset 違反文件 10 §4.6；`total` 會洩漏授權範圍外的長者數量。
- **不得包含 Restricted Data**：逐字稿、ASR 信心值、內部筆記、未覆核事件、
  診斷式分數、Secret、完整 Prompt。家屬版尤其要對照 §4 的零容忍清單。
- 錯誤訊息欄位不得回填被拒絕的原值，若該值本身是敏感資料。
- `security` 區塊描述的是**目標形狀**；若驗證器尚未實作，必須在 description 明說，
  不得讓讀者以為 JWT 已經會被驗證。

### 範例

- `examples/valid/` 至少一個，代表正常回應。
- `examples/invalid/` 至少一個，且**必須帶 `_why_invalid` 欄位**說明為何該被拒絕。
- invalid 範例通過驗證＝schema 太寬鬆，視同測試失敗。這些範例的用途是把
  「差點寫錯的地方」變成由測試守著，不是湊數。

## 8.2 何時要新增或更新 Contract

### 必須新增

- 新 endpoint、新 Domain Event、新 Agent Tool **實作完成之後、合併之前**。
- 既有 endpoint 新增欄位、新增狀態碼、或改變分頁／篩選行為。
- 新增 enum 值（同時檢查 §9 的 baseline 對齊要求）。

### 不得新增

- **尚未實作的 API 不寫進 contract**（§1）。需要先給前端一個形狀時，寫進
  `docs/` 的設計文件或 spec，不要放進 `contracts/`——`contracts/` 的語意是
  「這個可以現在打」。
- 不要為了讓驗證通過而放寬 schema。schema 與實作不符時，先判斷哪一邊錯了。

### 更新既有 contract

先判斷變更類型（文件 10 §22）：

| 類型 | 例子 | 做法 |
| --- | --- | --- |
| 相容 | 新增選填欄位、新增 enum 值、放寬長度上限 | 直接改，同一 major |
| 破壞性 | 刪欄位、改欄位名、改型別、收緊 enum、改 envelope 結構 | 走 Deprecation 流程，新 major |

破壞性變更依 §8 的規則：Consumer 先支援新舊版本，Producer 才切換。

### 流程

1. 確認實作真的完成，且能實際呼叫。
2. 改／新增 `schemas/` 底下的 JSON Schema。
3. 改 `openapi/`，以 `$ref` 指向 schema，不要把 schema 內嵌重複一份。
4. 補 `examples/valid/` 與 `examples/invalid/`。
5. 兩支驗證都要通過，缺一不可：

```powershell
uv run --with pyyaml --with jsonschema --with referencing python scripts/validate_contracts.py contracts

cd services/core-api
$env:DATABASE_URL = "postgresql+asyncpg://kinsun:kinsun_local_dev@localhost:5432/kinsun"
uv run --with pyyaml --with jsonschema --with referencing python ../../scripts/verify_contract_live.py ../../contracts
```

第 2 支是對**執行中的服務**驗證。沒有跑過它的 contract 不算數——契約的價值在於
它與現實一致，只通過自我驗證的契約只是散文。新增 endpoint 時，記得同步在
`scripts/verify_contract_live.py` 加上對應檢查，否則它永遠只驗舊的那幾條。

6. 若變更牽涉 `DIVERGENCE.md` 列出的任何一項，同步更新該檔。

## 8.3 回應與例外處理慣例

契約要能穩定，回應與錯誤的組裝方式就必須只有一條路。

- 對外 API 一律以 `SuccessEnvelope` / `ErrorEnvelope`（`app/core/envelopes.py`）
  作為統一回應格式，不得讓任何 endpoint 自行拼裝頂層結構。
- 服務層可以保留 `AuthorizedEldersResult` 這類明確的資料容器（frozen dataclass）
  來表達方法回傳結果。**服務層回傳 domain 型別，由 API 層轉成 envelope**，
  不要讓 service 認識 HTTP。
- **不要在 service 層拼裝 HTTP 錯誤 payload**。一律拋 `DomainException` 的子類，
  由 `app/api/error_handlers.py` 統一轉為 `ErrorEnvelope` 與對應狀態碼。
- 例外流程固定為：`DomainException → error_handlers → ErrorEnvelope`。
  這樣狀態碼對應只有一份（`EXCEPTION_MAP`），不會每個 endpoint 各寫一套而逐漸分歧。
- 非 `DomainException` 的例外若需要特定狀態碼，要在 `register_exception_handlers()`
  明確註冊，否則會掉進 catch-all 變成 500。已知案例：
  `NoAuthenticatorConfiguredError` 必須是 401（fail closed），不是 500。
- 錯誤訊息在 production 會經 `_sanitize_message()` 過濾；不要依賴訊息內容傳遞
  結構化資訊，那是 `code` 與（待補的）`reason_code` 的職責。

## 9. 程式與 Repository 工作方式

- 在技術選型尚未核准前，不要自行決定或鎖定 Python Framework、Frontend Framework、Package Manager、AWS Region 或外部 Provider。IaC 已由 ADR 0007 選定 AWS CDK v2；staging region 固定 `us-west-2`，production region 仍待核准。
- 若任務需要做出上述選擇，提出候選、Trade-off 與 ADR，取得明確決策後再建立骨架。
- Monorepo 已依文件 12 建立 `/apps`、`/services`、`/contracts`、`/infra`、`/data`、`/evals`、`/tests`、`/ops`、`/scripts`。在 Framework 與 Deployment 設計核准前，只維持中立的服務／責任邊界，不加入框架專屬內部結構。
- 目前本機基礎設施由 `docker-compose.yml`、`.env.example` 與 `docker/postgres/init/` 定義：
  - PostgreSQL 16 是本機交易資料庫。
  - `pgcrypto`、`citext` 由初始化腳本安裝。
  - 初始化腳本只處理資料庫／Extension，不得成為第二個 Schema Source of Truth。
  - `.env` 不進版控；新增設定時同步維護無 Secret 的 `.env.example`。
- Core API 已定案，程式在 `services/core-api/`：
  - 套件與環境管理採 uv（[ADR 0001](docs/adr/0001-package-manager-uv.md)）；`uv.lock` 必須進版控。
  - Web Framework 採 FastAPI ＋ SQLAlchemy 2.0 async（[ADR 0003](docs/adr/0003-core-api-framework-and-schema-authority.md)）。
  - 兩個 driver 並存且刻意如此：Alembic 用同步的 psycopg，應用層用非同步的 asyncpg。
    `DATABASE_URL` 只維護一份，寫成 asyncpg 形式，`alembic/env.py` 自行轉換。
  - Table／Index／Constraint／Trigger 一律由 Alembic 管理，PostgreSQL schema 名稱為 `eldercare_ai`。
  - v0.1 baseline 是凍結的 SQL 快照並以 SHA-256 驗證（[ADR 0002](docs/adr/0002-alembic-baseline-strategy.md)）。
    已套用的 migration 不可變；要改 schema 就新增 revision。
  - Windows checkout 可能把 baseline SQL 從 LF 轉成 CRLF，導致內容看似相同但 SHA-256
    驗證失敗。`.gitattributes` 必須維持
    `services/core-api/alembic/versions/sql/*.sql text eol=lf`；遇到 checksum 不符時，
    先檢查並將工作樹換行正規化為 LF，不得修改凍結 SQL 內容或預期 checksum 來讓驗證通過。
  - ORM model 的 Python 屬性統一是 `id`，實際對應各表自己的 PK 欄位（`__pk_name__`）。
    新增 model 時必須宣告 `__pk_name__`，否則 SQLAlchemy 會在 class 建立時失敗。
  - **domain enum 的每個值都必須在 baseline 中存在**（PG ENUM 的 label 或 CHECK 的允許值）。
    加了沒有 migration 的值，錯誤會在 INSERT 當下才爆，不是驗證期。
  - models 目前只涵蓋 48 張 baseline table 中的 33 張，`alembic revision --autogenerate`
    仍會把未映射 table 誤判為應刪除；產生的 migration 一律需人工檢查後才可使用。
- 前端已定案，程式在 `packages/frontend/`（[ADR 0006](docs/adr/0006-frontend-stack-and-app-topology.md)）：
  - Next.js 16 App Router + React 19 + TypeScript。**不是 Vite，不用 Tailwind**；
    樣式一律 CSS Modules ＋ `src/app/tokens.css` 的 CSS 變數。
  - TypeScript 側用 npm workspaces（根 `package.json` ＋ `package-lock.json`），
    與 Python 側的 uv 不共用。
  - 視覺、RWD 與無障礙規範見 [`design-system/MASTER.md`](design-system/MASTER.md)，
    建立任一頁面前先讀。元件內不得出現 raw hex（MASTER.md §14）。
  - 前端是 BFF：OAuth code exchange 與 access token 只存在伺服器端，
    token 不得進入瀏覽器可讀的位置。`src/app/backend/core/[...path]` 以 header
    allowlist 轉發，**不轉發 cookie**；新增轉發欄位前先確認不會夾帶憑證。
  - 家屬端的資料紅線（MASTER.md §11）在前端也要擋一次，不得只依賴後端不回傳。
  - UI 語言切換（`src/lib/i18n/`）只改瀏覽器偏好，**不得寫入任何 domain state**，
    尤其不得改動長者語言偏好或 consent。新增使用者可見字串時同時補 `zh-Hant` 與 `en`。
- 優先做最小、可測試、可回復且能貫穿 Vertical Slice 的變更。
- 不進行與任務無關的大規模重構、格式化、依賴升級或文件重寫。
- 保留使用者既有變更；不要以 Reset、Checkout 或大量覆寫清除未知修改。
- 任何變更需要 Push 到遠端時，必須先從最新的 `origin/main` 建立新的工作分支；
  禁止直接 Push `main`，也不得沿用混有其他任務變更的既有分支。
- 任何狀態或契約變更都同步更新相關 Schema、Test、Traceability 與必要文件。

## 10. 驗證與完成條件

每個變更至少驗證：

- Acceptance Criteria 的正常、低信心、拒絕、撤回、失敗與重試路徑。
- Cross-elder／Cross-tenant／Expired assignment／Revoked share 的 Negative Test。
- Unconfirmed Memory、Unreviewed Event 與 Draft Report 無法進入正式讀取路徑。
- Agent Tool Allowlist、Schema、Max-step、Timeout、Fallback 與 Core reauthorization。
- Outbox、Consumer Idempotency、DLQ、Projection Lag 與 Rebuild 行為。
- Delete／Revoke 後資料不會被 Retry、Replay 或 Restore 復活。
- Log、Metric、Trace 與 Error Response 不含 Restricted Data。
- 所有測試資料均為 Synthetic／De-identified。

不要虛構測試結果。

`services/core-api`：

```powershell
cd services/core-api
uv sync --extra test --extra dev
uv run pytest tests/unit          # 不需資料庫
uv run pytest tests/integration   # 需要 docker compose up -d postgres
uv run ruff check .
uv run ruff format --check .
```

`services/agent-runtime`（不需資料庫、AWS 憑證或網路）：

```powershell
cd services/agent-runtime
uv sync --extra test --extra dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

兩個服務各自維護 `pyproject.toml` 與 `uv.lock`，不共用虛擬環境。
其餘服務目錄尚無程式碼。

整合測試會對 `TEST_DATABASE_URL` 指向的資料庫執行 `alembic upgrade head`，
預設是 `kinsun_test`，不要指向 `kinsun`。測試資料全部由 fixture 產生，
均為 Synthetic，不得改用任何真實長者資料。

尚未建立的項目（不要描述成已完成）：Type Check（mypy／pyright）、跨服務 Contract Test、
E2E Test、CI Quality Gate。

Contract 驗證分三支：`scripts/validate_contracts.py` 驗 schema 與範例的自我一致性
（會掃 `contracts/openapi/` 底下所有文件）；`scripts/verify_contract_live.py` 對執行中的
core-api 驗證；`scripts/verify_agent_contract_live.py` 對執行中的 agent-runtime 驗證
（不需資料庫、憑證或網路）。新增 endpoint 時要同步在對應那支加檢查，否則它永遠只驗舊的。

每次變更至少執行：

```powershell
docker compose config --quiet
git diff --check
git status --short
```

動到 Database Schema 時另外執行（文件 13 §六.6：CI 需能從空 DB 重建）：

```powershell
docker compose up -d postgres
docker compose run --rm migrate alembic downgrade base
docker compose run --rm migrate                          # upgrade head
docker compose run --rm migrate alembic current
```

並在交付說明中清楚列出已驗證、未驗證與受環境限制的項目。

## 11. 仍待 ADR／Owner 決策

- Production AWS Region、Account／Environment 策略；staging 已固定 `us-west-2`。
- staging application 已限制每個 service 0／1 task、每個 task 0.5 vCPU／1 GiB；月費上限與
  24/7 或 demo-hours 運行方式仍待決。Aurora foundation 已固定 min 0／max 1 ACU、15 分鐘
  auto-pause；只有 CloudWatch／RDS 實測才可宣稱已成功降至 0 ACU。
- Bedrock Model／Inference Profile 與 Fallback。
- Neptune、OpenSearch、LINE、Email、Custom ASR／TTS 採真實服務或 Demo Adapter。
- Production API／Event／Client 支援期限。
- 正式 Retention、Export、Legal Hold 與 Offboarding 政策。
- 統一的 Voice／Agent／TTS Performance Gate。

不要用暫時實作偷偷取代這些決策；暫時方案必須標示 Owner、Expiry、Fallback 與移除條件。

## API 回應與錯誤處理建議

- 對外 API 請維持使用 `SuccessEnvelope` / `ErrorEnvelope` 作為統一回應格式。
- 服務層可保留像 `AuthorizedEldersResult` 這類明確資料容器（例如 dataclass）
  來表達方法回傳結果。
- 不要在 service 層手工組裝 HTTP 錯誤 payload；統一拋 `DomainException`，
  由全域 exception handler 轉為 `ErrorEnvelope`。
- 例外流程統一為：`DomainException -> error_handlers -> ErrorEnvelope`，避免在每個 endpoint 重複錯誤轉換邏輯。
