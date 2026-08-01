# Agent Runtime Service


成員 C（Agent／RAG／Graph）的服務，目前保留 M0 Agent 閉環，並新增一條受控的
`create_event_candidate` Core Tool 寫入路徑。
規則見 [`AGENTS.md`](AGENTS.md)，架構見
[`docs/architecture/agent-runtime-overview.md`](../../docs/architecture/agent-runtime-overview.md)。

## Endpoints

- `GET /health`
- `POST /api/v1/agent/runs`

契約在 [`contracts/openapi/agent-runtime.v1.yaml`](../../contracts/openapi/agent-runtime.v1.yaml)。

## 執行

```powershell
cd services/agent-runtime
uv sync --extra test --extra dev
uv run uvicorn --app-dir src agent_runtime.app:app --reload --port 8000
```

一般無 Tool 的本機回合不需要資料庫、Core API、AWS 憑證或網路。
若 `allowed_tools` 明確包含 `create_event_candidate`，Safety 允許且 Event Extractor 真的產生
Candidate，Runtime 才會要求 `CORE_API_BASE_URL`，向 Core 註冊正式 UUID AgentRun，並把該
UUID 放入 `ToolRequest.agent_run_id` 後執行 Core Tool。Runtime 不建立或保存 service token；
它只轉交呼叫端既有的 `Authorization`，由 Core 重新驗證 `SYSTEM_SERVICE`、tenant／elder／
session／policy、consent、scope 與 idempotency。缺少 Core 設定、Core 拒絕或 transport／
protocol 失敗一律 503 fail closed，不會用本地 `run-<UUID>` 寫入。

```powershell
curl http://localhost:8000/health
```

## 測試

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .

# 對執行中的服務驗證契約
uv run --with pyyaml --with jsonschema --with referencing python ../../scripts/verify_agent_contract_live.py ../../contracts
```

## 設計要點

- **Contract first**：Pydantic model 與 `contracts/schemas/` 的 JSON Schema 必須一致，
  由 `tests/unit/test_contract_schema_consistency.py` 守著。
- **一般 M0 對話不持久化**；只有實際執行 allowlisted Candidate Tool 時，才先建立
  Core-owned AgentRun。模型仍走 `MockModelProvider`，規則式輸出，不是語言模型。
- **Safety 是第一版 deterministic 關鍵字規則**，不是完整安全機制。命中時回 200、
  `result_status` 為 `BLOCKED`、`reply_text` 換成安全訊息——拒絕是對話結果，不是傳輸錯誤。
- **Orchestrator 保持單一模型決策**，並最多執行一次 deterministic Candidate Tool；沒有
  自由 Tool loop、Agent Debate 或未受控重試。
- 外部服務只能出現在 `models/provider.py`、`core/` 或 `tools/` 的 Adapter 邊界。

## 尚未實作

通用多 Tool 執行迴圈、Memory Candidate、RAG／Graph 查詢、Prompt Registry、Model Router、
AgentRun 終態回寫、Agent Trace 持久化、Evaluation。

`contracts/schemas/agent/HandoffEnvelopeV1` 仍是目標形狀；`contracts/schemas/tools/` 現已由
受控的 Core Tool adapter 使用，但目前只接通 `create_event_candidate`。
