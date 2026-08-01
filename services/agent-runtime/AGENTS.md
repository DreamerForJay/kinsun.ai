# AGENTS.md — agent-runtime

本檔補充 repository 根目錄的 [`AGENTS.md`](../../AGENTS.md)，只涵蓋 `services/agent-runtime/`。
根目錄那份的規則一律適用；兩者衝突時以根目錄為準。

負責範圍與邊界見 [`docs/ownership/member-c-scope.md`](../../docs/ownership/member-c-scope.md)。

## 目前狀態

M0 Foundation。可執行的最小閉環：HTTP → contract 驗證 → Orchestrator → Companion Agent
→ Safety Evaluator → 回應。模型走 `MockModelProvider`，**不呼叫任何外部 LLM**。

目前只接通一條受控 Tool 路徑：request `allowed_tools` 明確包含
`create_event_candidate`、Safety 為 `ALLOW` 且 deterministic Event Extractor 產生 Candidate
時，Runtime 先向 Core 註冊正式 UUID AgentRun，再以同一 UUID 呼叫 Core Tool。這不是通用
Tool loop；Runtime 不建立 service credential，只轉交呼叫端既有 Authorization，由 Core
重新驗證所有正式 scope。

尚未實作（不要描述成已完成）：Memory Candidate、Knowledge Retrieval Planner、Model Router、
Prompt Registry、Agent Trace 終態持久化、OpenSearch、Neptune、通用 Tool 執行迴圈、
Evaluation。

## 硬性規則

- **不得讓 Agent 直接改變正式 Domain State**。Event 轉 `VERIFIED`、Memory 轉 `ACTIVE`、
  Consent 變更、Report 發布，一律透過 Core API 的 Command Gate，由 Core 重新授權。
- **不得繞過 ElderScope、Consent 或 Authorization**。本地用 Mock 不是省略這些檢查的理由。
- **不得跨 `elder_id` 或 `tenant_id` 讀取資料**。
- **未確認的 Memory 不得進入 Context**。
- **不得產生可執行的 SQL、Gremlin 或 OpenSearch DSL**。查詢一律走參數化的 Planner。
- **不得建立無上限的 Agent Loop**。每條控制流都要有 step 上限與明確停止條件。
- 所有 Agent 輸出必須同時通過 Pydantic model 與 `contracts/schemas/` 的 JSON Schema。
- 不得在 Prompt、測試、fixture 或 log 放入真實個資。測試資料一律 Synthetic。
- Contract 不明確時使用 Adapter／Stub，不自行發明跨團隊 Contract。

## 實作慣例

- **Contract first**。`contracts/schemas/agent/`、`contracts/schemas/tools/` 的 JSON Schema
  與 `src/agent_runtime/contracts/models.py` 的 Pydantic model 必須一致，由
  `tests/unit/test_contract_schema_consistency.py` 守著（含 `additionalProperties: false`
  對應 `extra="forbid"`）。
- **外部服務只在 Provider／Adapter 邊界出現**。目前只有 `models/provider.py` 的
  `ModelProvider` 介面與 `models/mock_provider.py`。接 Bedrock、OpenSearch、Neptune 時
  新增實作，不要把 SDK 呼叫散進 orchestration 或 agent 層。
- Step／Tool 上限來自 `settings.py`：`MAX_AGENT_DECISIONS`、`MAX_TOOL_ROUNDS`、
  `MAX_TOTAL_TOOLS`、`MAX_REWRITE`。目前 companion 仍只有單一模型決策；受控 Candidate
  路徑會以 `MAX_TOOL_ROUNDS`／`MAX_TOTAL_TOOLS` 作 fail-closed gate 且最多呼叫一次 Tool。
  `MAX_REWRITE` 尚未有程式使用，不要誤以為已實作 rewrite loop。

## 對外 API 慣例

依 [ADR 0005](../../docs/adr/0005-agent-runtime-api-conventions.md)：

- 路徑 `/api/v1/agent/runs`；`/health` 維持在根層。
- 成功回應 `{"data", "meta"}`、錯誤回應 `{"error"}`，型別在
  `core/envelopes.py`，JSON Schema 共用 `contracts/schemas/common/`。
  **不要讓任何 endpoint 自行拼裝頂層結構。**
- 錯誤一律 `DomainError → api/error_handlers.py → ErrorEnvelope`。狀態碼對應只有一份
  （`EXCEPTION_MAP`）。不在 endpoint 或 orchestrator 裡組裝 HTTP 錯誤。
- `EXCEPTION_MAP` 沒收錄的 `DomainError` 子類會變成 500——這是刻意的 fail loud，
  新增例外時要同步登記。
- **錯誤回應不得回填被拒絕的值**。request body 是長者逐字稿；`details[].reason` 只帶
  pydantic 的 error type，不帶內容。

安全阻擋是 200 不是錯誤：`result_status` 為 `BLOCKED`、`reply_text` 換成安全訊息。
拒絕是對話結果，長者仍然會收到回覆。

## 測試

```powershell
cd services/agent-runtime
uv sync --extra test --extra dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

不需要資料庫、不需要 AWS 憑證、不需要網路。

`tests/unit/test_contract_schema_consistency.py` 掃的是 repository 根目錄的
`contracts/schemas/`，因此它同時會驗證 core-api 的 schema 是否為合法的 JSON Schema。
core-api 那邊加了壞掉的 schema，這裡會紅——這是刻意保留的交叉守護。

改到 endpoint 或回應形狀時，另外跑 live 驗證（AGENTS.md §8.2）：

```powershell
cd services/agent-runtime
uv run --with pyyaml --with jsonschema --with referencing python ../../scripts/verify_agent_contract_live.py ../../contracts
```

它對**實際執行中的服務**驗證，包含安全阻擋回合仍是 200、超過 step 上限走 domain
handler 而非 catch-all、以及錯誤回應不回填被拒絕的輸入。新增 endpoint 要同步在裡面加檢查。
