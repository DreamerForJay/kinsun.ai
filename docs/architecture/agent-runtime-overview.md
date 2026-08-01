# Agent Runtime 架構總覽

`services/agent-runtime/` 的 M0 Foundation。目標是在不依賴任何 AWS 服務的前提下，
先把邊界、請求流程、契約驗證與測試策略立起來。

```text
HTTP Request
  → CorrelationIdMiddleware
  → Contract validation (Pydantic + JSON Schema)
  → Orchestrator
      → explicit knowledge purpose? → staging Retriever
          → SUCCESS: 3–5 個限長、帶引用 chunk → Context Manifest
          → NO_DATA/FAILED: no-guess SAFE_FALLBACK（不呼叫 ModelProvider）
      → Companion Agent → ModelProvider
  → Safety Evaluator
  → allowed RAG reply: deterministic citation append
  → SuccessEnvelope

例外路徑：DomainError → error_handlers → ErrorEnvelope

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
| Orchestration | Agent 選擇、step 控制、Safety gate、狀態組裝 | `src/agent_runtime/orchestration/` |
| Agent | Companion Agent、Safety Evaluator | `src/agent_runtime/agents/` |
| Context | Context Manifest 建構（僅記憶體，無持久化） | `src/agent_runtime/context/` |
| Model | Provider 介面與 Mock 實作 | `src/agent_runtime/models/` |
| Tracing | `trace_id`、`agent_run_id` 產生器 | `src/agent_runtime/tracing/` |
| RAG | Bedrock query embedding、受控 hybrid plan、OpenSearch adapter、引用與 fallback | `src/agent_runtime/rag/` |

Agent Run 的 RAG intent gate 目前只接受明確的 `general_information` 或 `legal_reference`
purpose，不以自由文字猜測意圖。這讓一般 `conversation` 維持原流程，也讓知識檢索不可用時
能明確 fail closed。現有 Mock Model 不會理解 RAG context；測試只證明 chunk 已進入 provider
邊界、引用一定附在允許送出的回覆，以及 fallback 不會呼叫 provider 亂答。

## 為什麼沒有迴圈

M0 只跑一個決策步。沒有 Tool round、沒有 rewrite 路徑，第二輪會重跑一模一樣的
deterministic 流程，不可能改變結果，所以 orchestrator 是明確的單步執行而非迴圈。

這取代了原本的 `while True`——它的結尾是一個有條件 `break` 緊接一個無條件 `break`，
迴圈永遠只跑一輪，`StepLimitError` 永遠不會觸發，step 上限實際上是靠 API 層的重複前置
檢查達成的。真正會消耗 `MAX_TOOL_ROUNDS` 與 `MAX_REWRITE` 的多步迴圈，要與 Tool
執行引擎一起設計。

## Adapter 邊界

外部服務只能在這裡出現：

- `models/provider.py` — `ModelProvider` 介面
- `models/mock_provider.py` — 目前唯一實作，規則式輸出，不呼叫外部 LLM
- `rag/query_embedder.py` — Bedrock query embedding adapter
- `rag/client.py` — SigV4 OpenSearch adapter

接其他 Bedrock／AgentCore 模型或 Neptune 時新增 Provider／Adapter 實作，
由設定切換。**不要把 SDK 呼叫散進 orchestration
或 agent 層**，否則之後無法在沒有 AWS 憑證的環境跑測試。

## Context Manifest 的資料敏感度

`ContextManifestV1` 的 `items[].content` 目前直接放使用者輸入（逐字稿）。
現況是安全的——manifest 只存在於記憶體，API 回應只帶 `context_manifest_id`，
不回傳 manifest 本體。

但 `HandoffEnvelopeV1` **內嵌了整份 manifest**。一旦 handoff 真的跨服務傳遞，
逐字稿就會離開本服務，牴觸根目錄 `AGENTS.md` §8.1「contract 不得包含 Restricted Data」。
在那之前必須先決定：manifest 改成只帶 reference，或在 schema 標註 Restricted 並限制傳遞路徑。

## 目前不存在的東西

Tool 執行引擎、Event Extractor、Memory Candidate、Graph 實際查詢、
Prompt Registry、Model Router、Agent Trace 持久化、Evaluation runner，以及 production RAG。
Staging RAG 的程式路徑已存在，但 supplied Allowlist 尚未簽署、Human Review 未完成。
Staging 只有在 `RAG_REQUIRE_OWNER_SIGNATURE=false` 時可採 unsigned development override；
`RAG_ALLOWLIST_EXPECTED_SHA256` 必須由外部提供且完全相符，來源、Chunk、數量與完整
Allowlist 驗證仍不可略過。此路徑的 receipt／log 必須記錄
`governance_status=UNSIGNED_DEVELOPMENT_OVERRIDE` 與 `production_approved=false`。
Override 永不構成 production 核准；production 仍要求正式簽署，並須明確啟用
`RAG_PRODUCTION_ENABLED=true`。目前也沒有可驗證的 AWS/OpenSearch 環境，因此不得描述成
Human Review 或外部部署已完成。

`contracts/schemas/tools/` 已有 `ToolRequestV1`／`ToolResponseV1`，但**沒有任何程式使用它們**。
