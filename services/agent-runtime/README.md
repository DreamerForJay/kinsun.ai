# Agent Runtime Service

成員 C（Agent／RAG／Graph）的服務，目前是 M0 Foundation。
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
uv run uvicorn --app-dir src agent_runtime.app:app --reload --port 8001
```

不需要資料庫、AWS 憑證或網路。

```powershell
curl http://localhost:8001/health
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
- **M0 沒有持久化、沒有外部依賴**。模型走 `MockModelProvider`，規則式輸出，不是語言模型。
- **Safety 是第一版 deterministic 關鍵字規則**，不是完整安全機制。命中時回 200、
  `result_status` 為 `BLOCKED`、`reply_text` 換成安全訊息——拒絕是對話結果，不是傳輸錯誤。
- **Orchestrator 是明確的單步執行**，不是迴圈。原因見架構文件「為什麼沒有迴圈」。
- 外部服務只能出現在 `models/provider.py` 的 Provider 邊界。

## 尚未實作

Tool 執行引擎、Event Extractor、Memory Candidate、RAG／Graph 查詢、Prompt Registry、
Model Router、Agent Trace 持久化、Evaluation。

`contracts/schemas/agent/HandoffEnvelopeV1` 與 `contracts/schemas/tools/` 兩支是**目標形狀**，
沒有任何程式使用，也刻意不寫進 OpenAPI。
