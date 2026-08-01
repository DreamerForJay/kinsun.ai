# Contracts

機器可驗證的 API 契約。依 AGENTS.md §8，OpenAPI 3.1、AsyncAPI 與 JSON Schema 是契約來源，
不是說明文件。

## 目前有什麼

```
contracts/
├── openapi/
│   ├── core-api.v1.yaml              OpenAPI 3.1，41 個已實作的 path
│   └── agent-runtime.v1.yaml         OpenAPI 3.1，3 個已實作的 endpoint
├── asyncapi/
│   └── core-events.v1.yaml           AsyncAPI 3.x，Core Domain Event channel
├── schemas/
│   ├── common/                       共用 response envelope
│   ├── domain/                       Core request／response DTO
│   ├── events/                       Domain Event Envelope、publisher／consumer failure outcome
│   ├── agent/                        AgentRunRequest／Response、ContextManifest、
│   │                                 HandoffEnvelope、SafetyEvaluation
│   ├── rag/                          Staging chunk／metadata、ingestion receipt、
│   │                                 retrieval request／response
│   └── tools/                        Core ToolRequest／ToolResult、legacy ToolResponse
├── examples/
│   ├── valid/                        必須通過驗證的範例
│   └── invalid/                      必須被拒絕的範例
└── DIVERGENCE.md                     與文件 10 的差異清單
```

兩個服務的 endpoint 都採同一組 envelope：成功是 `{"data", "meta"}`，錯誤是 `{"error"}`，
`common/` 的 `ResponseMetaV1` 與 `ErrorEnvelopeV1` 由兩邊共用而非各自複製一份
（[ADR 0005](../docs/adr/0005-agent-runtime-api-conventions.md)）。

Agent Runtime 的第三個 endpoint 是 `POST /api/v1/rag/retrievals`。它只代表 staging
retrieval HTTP boundary 已可呼叫：未設定 Bedrock／OpenSearch 時仍回 HTTP 200，但
`data.status = FAILED`、`results = []` 並提供明確 fallback，Agent 不得據此猜測答案。
這不代表 staging ingestion、Human Review、production projection 或 deletion 已完成。

## §8.2 的明示例外

兩支 schema 描述的流程尚未接上 executable endpoint，依 AGENTS.md §8.2 在此明列為例外：

| Schema | 狀態 |
| --- | --- |
| `agent/HandoffEnvelopeV1` | 有 Pydantic model 與測試，但 orchestrator 從未產生 handoff |
| `tools/ToolResponseV1` | Agent Runtime 的 legacy target；Core endpoint 實際回傳 `ToolResultV1` |

Core 的 `ToolRequestV1`／`ToolResultV1` 已由 `POST /api/v1/internal/tools/execute` 實際使用；
`RegisterAgentRunRequestV1`／`AgentRunRegistrationV1` 與
`CompleteAgentRunRequestV1`／`AgentRunCompletionV1` 則分別描述 Tool 執行前的 Core-owned
registration 與執行後的 terminal compare-and-set completion。三個 endpoint 都列在
`core-api.v1.yaml`，不屬於例外。Agent Runtime 的受控 `create_event_candidate` 路徑已以
adapter 串起 register → Tool → complete；通用多 Tool 迴圈仍未實作，且不得把 legacy
`ToolResponseV1` 與 Core `ToolResultV1` 視為同一型別。

上述兩支例外 schema 不在 executable OpenAPI path 裡。
要判斷「這個能不能現在呼叫」，看 OpenAPI，不要看 `schemas/` 底下有沒有檔案。

## 重要前提

**這份契約以目前實作為準，不是以文件 10 為準。** 兩者有實質差異——envelope 結構、
錯誤欄位、狀態碼對應都不同。差異全部列在 [DIVERGENCE.md](DIVERGENCE.md)，
尚未決定要往哪邊收斂。改任何一邊之前先讀那份清單。

**Executable contract 只涵蓋已實作的 endpoint。** WebSocket audio transport、Care Action、
Notification delivery、正式 Agent Handoff／多步 Tool 迴圈、Graph／OpenSearch production projection
與 Cognito verifier 尚未完成；完整差異以 [DIVERGENCE.md](DIVERGENCE.md) 為準。

## invalid/ 範例的用途

`invalid/` 底下每個檔案都帶 `_why_invalid` 欄位，說明它為什麼必須被拒絕。
這些不是湊數用的——它們防止 schema 寫得太寬鬆：

- `elder-summary-bad-care-setting.json` — `BOTH` 是分支原本的 enum 值，
  但 `eldercare_ai` 的 CHECK 約束不接受。若 schema 放行，錯誤會延到 PostgreSQL 才爆。
- `actor-profile-legal-representative.json` — `LEGAL_REPRESENTATIVE` 不是 actor type
  而是關係類型（文件 06 §4.1）。這個範例讓該區分由測試守著，而不是靠記憶。
- `authorized-elders-offset-pagination.json` — offset 分頁與 total 筆數都違反
  文件 10 §4.6：可猜測的 offset 不得用於長者資料，total 會洩漏授權範圍外的長者數量。
- `tool-request-missing-consent-version.json` — 少了 `consent_version` 就無法在執行時
  重驗同意版本（AGENTS.md §5）。放行的話，同意被撤回後重播的呼叫與仍然有效的呼叫
  長得一模一樣，錯誤會延到執行期變成 consent bypass。
- `tool-response-missing-retryable.json` — 少了 `retryable`，agent 只能從 `status` 猜；
  但 `FAILED` 同時涵蓋暫時性逾時與永久性授權拒絕，猜錯就是重試一個 Core 已經拒絕的呼叫。

## 驗證

契約本身、範例、以及實際執行中的服務三者都要對得起來。

```powershell
# 1. schema 合法性、OpenAPI $ref 可解析、範例符合預期（掃 openapi/ 下所有文件）
uv run --with pyyaml --with jsonschema --with referencing python scripts/validate_contracts.py contracts

# 2a. core-api 實際回應是否符合契約（需要 postgres 容器）
cd services/core-api
$env:DATABASE_URL = "postgresql+asyncpg://kinsun:kinsun_local_dev@localhost:5432/kinsun"
uv run --with pyyaml --with jsonschema --with referencing python ../../scripts/verify_contract_live.py ../../contracts

# 2b. agent-runtime 實際回應是否符合契約（不需資料庫、憑證或網路）
cd services/agent-runtime
uv run --with pyyaml --with jsonschema --with referencing python ../../scripts/verify_agent_contract_live.py ../../contracts
```

第 2 項是關鍵：沒有對執行中的服務驗證過的契約只是散文。

## 新增 endpoint 時

1. 先確認它真的實作完成——契約不寫尚未存在的東西。
2. 在 `schemas/domain/` 新增 `<Name>V1.json`（PascalCase＋Version，文件 10 §3.1）。
3. 在 `openapi/core-api.v1.yaml` 加上 path，以 `$ref` 指向 schema。
4. `examples/valid/` 與 `examples/invalid/` 各補至少一個，invalid 要寫 `_why_invalid`。
5. 兩支驗證腳本都要通過。
