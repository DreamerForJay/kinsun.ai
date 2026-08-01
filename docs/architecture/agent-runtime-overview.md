# Agent Runtime 架構總覽

`services/agent-runtime/` 目前是 M0 Foundation，加上一條受控的 Event Candidate Core Tool
路徑。預設本機設定使用 `MockModelProvider`，可在沒有 AWS 服務的環境驗證主要邊界；程式另有
可設定的 Bedrock Converse provider 與 staging-only RAG adapter，但尚無真實 AWS staging 或
production runtime 驗證，不能把 adapter 存在描述成服務已部署。

```text
HTTP Request
  → CorrelationIdMiddleware
  → Contract validation (Pydantic + JSON Schema)
  → Orchestrator
      → explicit knowledge purpose? → staging Retriever
          → SUCCESS: 3–5 個限長、帶引用 chunk → Context Manifest
          → NO_DATA/FAILED: no-guess SAFE_FALLBACK（不呼叫 ModelProvider）
      → Companion Agent → configured ModelProvider
      → Safety Evaluator
      → allowed RAG reply: deterministic citation append
      → Safety ALLOW + allowlisted create_event_candidate?
          → deterministic Event Extractor
          → Core AgentRun register
          → ToolExecutor → Core Tool Gate → Event Candidate
          → Core AgentRun terminal complete
  → SuccessEnvelope

一般例外：DomainError → error_handlers → ErrorEnvelope
Core register／Tool／complete 依賴失敗：fail closed → sanitized 503

Staging RAG Request
  → RetrievalRequestV1
  → BedrockQueryEmbedder (`search_query`)
  → 受控 HybridSearch plan（固定 filter＋設定化權重）
  → OpenSearchClient
  → 3–5 個帶完整引用的 chunk，或明確 no-guess fallback
```

## 分層

| 層 | 內容 | 位置 |
| --- | --- | --- |
| Middleware | Correlation ID 產生與回傳 | `src/agent_runtime/middleware/` |
| API | `GET /health`、Agent Run、staging RAG Retrieval、例外處理 | `src/agent_runtime/api/` |
| Envelope | `SuccessEnvelope`／`ErrorEnvelope`（對應 `contracts/schemas/common/`） | `src/agent_runtime/core/envelopes.py` |
| Contract | Pydantic model；對應 `contracts/schemas/{agent,tools}/` 的 JSON Schema | `src/agent_runtime/contracts/models.py` |
| Orchestration | Agent 選擇、step 控制、RAG、Safety gate、受控 Candidate Tool lifecycle、狀態組裝 | `src/agent_runtime/orchestration/` |
| Agent | Companion Agent、deterministic Event Extractor、Safety Evaluator | `src/agent_runtime/agents/` |
| Context | Context Manifest 建構（僅記憶體，無持久化） | `src/agent_runtime/context/` |
| Model | Provider 介面、預設 Mock、可設定 Bedrock Converse adapter | `src/agent_runtime/models/` |
| Core integration | Core-owned AgentRun register／complete adapter | `src/agent_runtime/core/` |
| Tool | Allowlisted Core Tool request builder 與 executor；目前只接 `create_event_candidate` | `src/agent_runtime/tools/` |
| Tracing | `trace_id`、本地識別碼工具；正式 Candidate run ID 由 Core 建立 | `src/agent_runtime/tracing/` |
| RAG | Bedrock query embedding、受控 hybrid plan、OpenSearch adapter、引用與 fallback | `src/agent_runtime/rag/` |

Agent Run 的 RAG intent gate 目前只接受明確的 `general_information` 或 `legal_reference`
purpose，不以自由文字猜測意圖。這讓一般 `conversation` 維持原流程，也讓知識檢索不可用時
能明確 fail closed。預設 Mock provider 不理解 RAG context；設定式
`BedrockModelProvider` 會讀取 Context Manifest 中的 approved excerpts，仍須經 deterministic
Safety 與 citation 後處理。這只證明 adapter 與離線測試邊界存在，不代表真實 Bedrock、
OpenSearch 或 production Guardrails 已驗證。

## 為什麼沒有通用迴圈

目前 Companion 固定只跑一個 bounded model decision。若 Safety 允許、request 明確 allowlist
`create_event_candidate`，且 deterministic Event Extractor 確實產生 Candidate，才最多執行一次
Core Tool。`MAX_TOOL_ROUNDS` 與 `MAX_TOTAL_TOOLS` 在這條路徑只作 fail-closed gate；
`MAX_REWRITE` 尚未被執行流程使用。

因此目前不是通用多 Tool 迴圈，也沒有自由重試、Agent Debate 或 cross-agent handoff。真正會
消耗多輪 Tool／rewrite budget 的控制流程，必須另行設計顯式停止條件、Core reauthorization
與可測試的 failure state，不能把現有單次 Candidate 路徑描述成已完成的 Tool engine。

## 受控 Event Candidate Tool 路徑

只有以下條件全部成立才會嘗試正式 Candidate 寫入：

1. `allowed_tools` 明確包含 `create_event_candidate`。
2. Safety decision 是 `ALLOW`。
3. deterministic Event Extractor 產生符合 schema 的 Candidate。
4. `session_id`、`elder_id`、`consent_version` 與必要識別碼格式有效。
5. Runtime 能向 Core 註冊正式 UUID AgentRun。

Runtime 以同一個 Core-owned AgentRun UUID 執行 allowlisted Tool，並同步完成 terminal state。
它不自行建立正式 Domain State、不信任 request body 的 actor／tenant／scope，也不建立 service
credential；現行 adapter 只轉交 caller 的 `Authorization`，由 Core 重新驗證 service identity、
tenant／elder／session／policy、Consent、授權、狀態與 idempotency。Core dependency、Tool 或
completion 失敗一律 fail closed，不會以本地 UUID 假裝成功。

## Adapter 邊界

外部服務只能在以下 Provider／Adapter 邊界出現：

- `models/provider.py` — `ModelProvider` 介面
- `models/mock_provider.py` — 預設本機規則式實作，不呼叫外部 LLM
- `models/bedrock_provider.py` — 可設定 Bedrock Converse adapter；model ID 仍是 Owner 決策
- `core/` — Core AgentRun register／complete adapter
- `tools/` — allowlisted Core Tool request／result adapter
- `rag/query_embedder.py` — Bedrock query embedding adapter
- `rag/client.py` — SigV4 OpenSearch adapter

接其他 Bedrock／AgentCore 模型或 Neptune 時新增 Provider／Adapter 實作，由設定切換。**不要把
SDK 呼叫散進 orchestration 或 agent 層**，否則之後無法在沒有 AWS 憑證的環境跑測試。

## Context Manifest 的資料敏感度

`ContextManifestV1` 的 `items[].content` 目前直接放使用者輸入（逐字稿）。現況下 manifest
只存在於記憶體，API 回應只帶 `context_manifest_id`，不回傳 manifest 本體。

但 `HandoffEnvelopeV1` **內嵌了整份 manifest**。一旦 handoff 真的跨服務傳遞，逐字稿就會
離開本服務，牴觸根目錄 `AGENTS.md` §8.1「contract 不得包含 Restricted Data」。在啟用
handoff 前，必須先決定 manifest 改成只帶 reference，或建立明確的 Restricted Data 傳輸、
授權與 retention 邊界。

## 目前不存在的東西

目前尚未實作：通用多 Tool 執行迴圈、Memory Candidate 與長者確認閉環、Graph／Neptune
實際查詢、Prompt Registry、Model Router、cross-agent handoff、完整 Agent Trace 持久化、
Evaluation runner，以及 production RAG／Guardrails。

Staging RAG 程式路徑雖已存在，supplied Allowlist 尚未簽署、Human Review 未完成，也尚無可
驗證的 AWS／OpenSearch 環境。Staging 只有在 `RAG_REQUIRE_OWNER_SIGNATURE=false` 時可採
unsigned development override；`RAG_ALLOWLIST_EXPECTED_SHA256`、來源、Chunk、數量與完整
Allowlist 驗證仍不可略過。Override 永不構成 production 核准。

`contracts/schemas/tools/` 的 Core `ToolRequestV1`／`ToolResultV1` 已由受控
`create_event_candidate` adapter 使用；`HandoffEnvelopeV1` 與 legacy `ToolResponseV1` 仍是
未接入 executable path 的目標形狀。
