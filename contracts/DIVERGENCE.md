# Contract 與文件 10 差異清單

- 更新日期：2026-08-01
- 文件基準：`docs/10智慧長照 AI 陪伴系統－API、Event、Tool 與 Data Contracts v0.1.md`
- 執行基準：目前 `services/core-api` 與 `services/agent-runtime`

`contracts/` 以目前可執行的介面為準；文件 10 同時包含目標設計。下列差異尚未全部收斂，Consumer 不得自行假設文件 10 已實作。

## 已在本次收斂

- 所有業務 API 成功回應都使用 `SuccessEnvelope`，並帶 `meta.schema_version = "1.0"`；`/health`、`/ready` 保持運維探針格式。
- 所有錯誤回應都使用 `ErrorEnvelope`，並帶穩定的 `reason_code` 與 `retryable`。
- Elder、Consent、Voice Session metadata、Care Event、Memory、Daily Summary、Family Report、Assignment、Deletion status 與受控 Tool endpoint 已列入 OpenAPI。
- Care Event 一般讀取只回傳 `VERIFIED`／`CORRECTED`，Daily Summary 一般讀取只回傳 `READY`／`PUBLISHED`；明確要求其他可覆核狀態時必須額外通過對應 review scope，長者本人不得取得照護者 review scope，單筆拒絕維持不可探測 404，`DELETED` Care Event 不會由讀取 API 回傳。
- JSON Schema 頂層採 `additionalProperties: false`；Care Event、Tool 與 Domain Event 會拒絕 transcript、audio、prompt、secret、token 等 Restricted Data 欄位。
- 新增 Domain Event Envelope、AsyncAPI 與 provider-neutral publisher／consumer failure contract；Outbox relay 與 Consumer 的 idempotent foundation 會在處理前重查 Consent、tenant scope、aggregate state 與通用 hash Tombstone，並以穩定 `reason_code`、`retryable`、attempt limit 與 `RETRY`／`DEAD_LETTER` 表達失敗，不保存原始 exception message。
- Contract validator 驗證 JSON Schema、OpenAPI、AsyncAPI、正常與刻意錯誤範例；live verifier 比對 runtime 與 contract operation，並抽查 GET endpoint 的 fail-closed 行為。

## 仍存在的差異

### Success metadata

目前：

```json
{
  "correlation_id": "...",
  "timestamp": "2026-07-31T04:12:09Z",
  "schema_version": "1.0"
}
```

文件 10 另要求 `request_id`、`trace_id`、`server_time`。目前 `timestamp` 承擔 server time；是否改名屬 envelope breaking change，需走版本與 Deprecation 決策。

### Pagination

目前 page metadata 位於 `data` 內，例如：

```json
{
  "data": {
    "items": [],
    "next_cursor": null,
    "has_more": false
  },
  "meta": {}
}
```

文件 10 將 `page` 放在 envelope 頂層。現況仍採 opaque cursor，沒有 `offset`、`page_number` 或 `total`，因此不會洩漏授權範圍外數量。調整 envelope 位置需新 major。

### Error envelope

目前 `code` 仍是依 HTTP status 產生的較粗粒度 slug；`reason_code` 才是穩定的細分原因。欄位名稱仍使用 `details`，尚未改為文件 10 的 `field_errors`／`safe_details`／`support_reference`。

### HTTP status

- Pydantic／semantic validation 目前皆為 422；文件 10 對部分 validation 使用 400。
- 未授權 elder scope 與不存在 elder 均回 404，以避免資源探測。
- 410、429、502、504 尚未建立對應 DomainException 與 endpoint 行為。

### Authentication

Core 已實作 Cognito JWT verifier，且以兩條明確分離的路徑使用：

- 一般 protected endpoint 只接受 Cognito Access Token，驗證 RS256／JWKS、issuer、expiry、
  `token_use=access` 與 `client_id`，再以 live Core DB 解析 actor、tenant 與 role；JWT claim
  不直接授權 elder scope。
- `POST /api/v1/onboarding/resolve` 只接受 Cognito ID Token，驗證 audience、
  `token_use=id` 與 verified email，再依 ELDER／FAMILY intent 建立或兌換正式 Core state。
  FAMILY intent 沒有有效一次性邀請碼時不會取得任何 elder access。
- Browser 透過 Next.js BFF 的 HttpOnly Cookie 傳遞 Access Token；OAuth callback 使用
  Authorization Code + PKCE，ID Token 只在 callback server-side 呼叫 onboarding resolver，
  不寫入 browser cookie。
- Development 仍只有在 `FAKE_AUTH_ENABLED=true` 時使用明確 fake actor；Cognito 關閉或
  設定不完整時 fail closed。

目前 contract 不代表 staging Cognito domain、Google provider secret、callback URL 或正式
Refresh Token rotation 已部署／驗證；這些仍須由環境設定與部署證據確認。

### Voice transport

Core 已實作 Voice Session metadata 與受控狀態轉移，但 WebSocket binary/audio transport、ASR Final、低信心確認與 TTS 仍屬 Speech workstream。回應明確標示 `transport_status = NOT_CONFIGURED`。

Core 另提供已實作的單輪文字 fallback：`POST /api/v1/voice-sessions/{session_id}/companion-turns`。
它會在 Core 重新檢查 tenant／elder scope、`BASIC_VOICE` Consent snapshot 與 Session state，
再以 server-to-server 方式呼叫 M0 Agent Runtime，保存不含輸入文字與回覆內容的 Agent／Safety
稽核 metadata，最後回傳 `transport_status = TEXT_ONLY`。這不代表 WebSocket、ASR 或 TTS 已完成。

### Deletion workflow

目前撤回同意可在同一交易建立 `deletion_request`、各 store job item 與 `deletion.requested.v1`；狀態查詢會回傳每個 item 的開始時間、attempt 與不含 Restricted Data 的 failure code。Core 另已實作 deterministic request／item state machine、tenant-scoped hash Tombstone、`MEMORY` 的 Aurora 內容清除，以及 relay／consumer replay suppression。只有可信 internal caller 提供核准的 policy version、retention basis 且 legal-hold 結果為 `CLEAR` 時才可執行；必要 item 未全部 `COMPLETED`／合法 `SKIPPED` 時只會是 `PARTIAL_FAILED`。

目前唯一已接上的實際清理 handler 是 Aurora `MEMORY`。S3、Neptune、OpenSearch、Cache、通知、備份與外部 Provider 尚未配置，嘗試處理會得到 `TARGET_NOT_CONFIGURED`，不得宣告全數刪除。文件 10 的獨立 deletion create API、internal retry endpoint、正式 retention／legal-hold authority、completion certificate 與外部 store verification 仍未實作，因此未列入 executable OpenAPI。

### Domain Event envelope

目前 ID 使用 UUID，`event_version` 使用整數 `1`，且沒有文件 10 範例中的 `producer` 欄位。正式 EventBridge／SQS binding、Queue、DLQ 與 Redrive 仍受 AWS environment／IaC 決策約束；現有 relay 與 consumer 是可測試的 provider-neutral foundation。

### Agent Handoff 與 Agent Runtime

`services/agent-runtime` 已有 M0 HTTP API 與對應 OpenAPI，但正式跨 Agent handoff、多步 Tool 迴圈及完整 Agent Handoff Result 尚未實作。`HandoffEnvelopeV1` 目前只有 model／schema，orchestrator 不會產生它；其內嵌 `context_manifest` 的形狀也仍與文件 10 只傳 `context_manifest_id` 的設計不同。

`AgentRunResponseV1` 是 Agent Runtime 的 HTTP 回應，不是文件 10 的 Handoff Result，不能用它代替 Handoff Result。現有 result status 只有 `SUCCESS`、`SAFE_FALLBACK`、`BLOCKED`、`FAILED`，尚未涵蓋文件 10 的 `NEEDS_CLARIFICATION`、`HUMAN_REVIEW`、`NO_DATA` 等狀態。

### Staging RAG retrieval

Agent Runtime 已實作 `POST /api/v1/rag/retrievals` 的 staging-only HTTP boundary，並使用
`SuccessEnvelope` 回傳 `RetrievalResponseV1`。未設定 Bedrock／OpenSearch、provider 失敗或
沒有足夠合格來源時，介面會 fail closed：HTTP 200 的 `data.status` 為 `FAILED` 或
`NO_DATA`、`results` 為空，並提供明確 fallback；不得由 Agent 猜測或把查詢字串回填到回應。

這個可執行 retrieval contract 不代表資料治理與 AWS 環境已完成：

- 現有 allowlist 狀態是 `DRAFT_FIXED_HASH_NOT_EFFECTIVE_UNTIL_PROJECT_OWNER_SIGNATURE`，
  `project_owner_risk_acceptance` 為 `NOT_SIGNED`。只有 staging 明確設定
  `RAG_REQUIRE_OWNER_SIGNATURE=false` 時，才允許以 unsigned development override 執行；
  外部提供且完全相符的 `RAG_ALLOWLIST_EXPECTED_SHA256`，以及來源、Chunk、數量與完整
  Allowlist 驗證仍全部強制執行。Override 的 receipt／log 必須標示
  `governance_status=UNSIGNED_DEVELOPMENT_OVERRIDE`、`production_approved=false`。
- `human_source_review` 仍是 `NOT_COMPLETED`；unsigned development override 不等於 Human
  Review，也不得宣稱 Human Review 已完成。
- Repository 不保存真實 AWS 金鑰，且目前沒有可供本次驗證的 AWS Account／Bedrock／
  OpenSearch staging 連線資訊，因此 executable contract 測試只驗證無設定時的安全 fallback，
  不宣稱已建立或驗證真實 index、alias、embedding 或文件數。
- allowlist 的 `production_status` 仍是 `BLOCKED`；unsigned development override 不得用於
  production。任何 production 執行仍須正式簽署 Allowlist，並明確設定
  `RAG_PRODUCTION_ENABLED=true`；此 endpoint 與目前相關設定不得當作 production RAG。
- Agent Runtime 尚未有服務對服務身分驗證；在 IAM／mTLS／service-token contract 定案前，
  這個 staging endpoint 只能置於受控私網，不能直接暴露到公網。`audience` 與 `purpose`
  目前只可信任已授權的內部 caller。
- Retrieval 是 staging knowledge read path，不是 Aurora outbox 驅動、可重建的正式
  OpenSearch projection，也不是 deletion workflow 的 OpenSearch 清理 handler。下方列出的
  projection endpoint 與上方 deletion 外部 store verification 仍未完成。

### Core Tool 與 Agent Tool schema

Core 已實作 `POST /api/v1/internal/tools/execute`，因此 `ToolRequestV1` 與 `ToolResultV1` 以 Core 的 Pydantic model 為 executable contract：

- request 使用 `parameters`，並由 Core 的可信服務身分解析 actor、tenant 與 trace context；不接受模型自行提供這些欄位。
- `consent_version`、`policy_version` 與 `request_id` 是必要欄位；寫入工具另以 `idempotency_key` 與 `expected_resource_version` 控制重播及併發。
- result 使用 `result_status`、`data`、`source_refs`、`reason_code`、`retryable` 與 `redactions`。

舊的 `ToolResponseV1` 是尚未接上 Core endpoint 的 Agent Runtime 目標格式，保留作為 migration input，不代表可呼叫的 API。它與 Core 的 `ToolResultV1` 在欄位名稱及 source reference 細節上仍不同，後續應由 Agent Runtime adapter 明確轉換，不可讓兩份 schema 共用同一 `$id` 或互相覆蓋。

## 尚未實作、不得視為 executable contract

- WebSocket voice event contract 與 audio upload。
- Care Action API。
- Notification delivery API／LINE／Email Adapter。
- 正式 Agent Handoff 與多步 Agent Tool 迴圈。
- Graph／正式 OpenSearch projection endpoint。

上述項目應留在 `docs/` 或各 Owner 的設計產物；只有已存在的 model/schema 例外必須在本文件明示，完成實作與 live verification 後才可升格為 executable contract。
