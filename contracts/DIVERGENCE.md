# Contract 與文件 10 差異清單

- 更新日期：2026-08-02
- 文件基準：`docs/10智慧長照 AI 陪伴系統－API、Event、Tool 與 Data Contracts v0.1.md`
- 執行基準：目前 `services/core-api` 與 `services/agent-runtime`

`contracts/` 以目前可執行的介面為準；文件 10 同時包含目標設計。下列差異尚未全部收斂，Consumer 不得自行假設文件 10 已實作。

## 已在本次收斂

- 所有業務 API 成功回應都使用 `SuccessEnvelope`，並帶 `meta.schema_version = "1.0"`；`/health`、`/ready` 保持運維探針格式。
- 所有錯誤回應都使用 `ErrorEnvelope`，並帶穩定的 `reason_code` 與 `retryable`。
- Elder、Consent、Voice Session metadata、Care Event、Memory、Daily Summary、Family Report、Assignment、Deletion status 與受控 Tool endpoint 已列入 OpenAPI。
- Care Event 一般讀取只回傳 `VERIFIED`／`CORRECTED`，Daily Summary 一般讀取只回傳 `READY`／`PUBLISHED`；明確要求其他可覆核狀態時必須額外通過對應 review scope，長者本人不得取得照護者 review scope，單筆拒絕維持不可探測 404，`DELETED` Care Event 不會由讀取 API 回傳。Care Event 的 `event_type`、`date_from`、`date_to` 會在 tenant／elder scope 內、opaque cursor 分頁之前由 repository 過濾；日期以 UTC `COALESCE(event_time, created_at)` 且含首尾日。
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

### LINE Login federation 與 Cognito 帳號連結

Next.js BFF 與 CDK 已加入 staging-only LINE Login OIDC federation。Cognito OIDC provider 固定使用
`https://access.line.me`，要求 `openid profile email`，且 Web BFF app client 同時支援 `Google` 與
自訂 `LINE` provider。因現有 User Pool 將 `email` 設為 required，LINE `email` claim 必須映射到
Cognito `email`；linking 前會先確認目前 Cognito email 已驗證且等於 LINE verify endpoint 回傳的
email。這個檢查只防止 federated attribute mapping 覆寫既有 recovery email，不會以 Email 尋找
Actor、連結兩個 Cognito users 或 merge 兩個 Actor；不相符時一律拒絕並要求人工處理。

安全連結流程只能由已登入且已連結 Google 的 Cognito user 發起，並使用獨立 10 分鐘 HttpOnly
signed transaction、state、nonce 與 PKCE S256。Transaction 只保存由獨立 secret 對發起者
Cognito username 產生的 domain-separated HMAC fingerprint，不保存 raw username、subject 或
email；callback 最終 AdminLink 前會重新比對，同瀏覽器中途切換帳號時一律拒絕並 revoke LINE
token。BFF 直接向 LINE 換 token、呼叫 LINE ID token
verify endpoint取得可信 `sub`，再以 IAM `cognito-idp:AdminLinkProviderForUser`、source
`Cognito_Subject` 連到目前 `GetUser` 回傳的 destination username。LINE token 不保存、不記錄，
並在流程結束 best-effort revoke。若 LINE subject 已屬於其他 Cognito user，系統拒絕轉移與 merge。
BFF 執行角色必須提供為 staging `LINE_LOGIN_BFF_ROLE_ARN`；CDK 只會在該既有 same-account
role 上加入目標 User Pool ARN 的 `cognito-idp:AdminLinkProviderForUser`，不授予
`Resource: *`。若 hosting 平台尚未建立穩定的 server execution role，LINE federation 設定會因
缺少此 ARN 而 fail closed，必須先完成 hosting role ownership。

一般 LINE sign-in 仍走 Cognito Hosted UI，但 callback 只用 Access Token 呼叫 Core
`GET /api/v1/me` 確認既有 `cognito_sub → Actor`；它絕不呼叫 onboarding resolver。User Pool 的
PreSignUp Lambda 另拒絕 Cognito 嘗試建立新的 `LINE_*` external-provider user，未連結 LINE Login
因此 fail closed。此 gate 是否在已連結 LINE identity 的 staging sign-in 中確實略過，以及 Google
federated destination username、LINE required-email mapping 的實際 Cognito 行為，仍須 live staging
測試，不得只憑 synth 宣稱完成部署驗證。

同一個 LINE Login Channel 必須登錄兩個固定 callback：Cognito domain 的
`/oauth2/idpresponse`，以及 frontend origin 的
`/backend/auth/identities/line/callback`。LINE Login Channel secret、LINE Messaging Channel
secret、LINE identity HMAC secret、一般 OAuth transaction secret 與 LINE linking transaction
secret必須彼此獨立。LINE Login identity 只存在於 Cognito federation；下節的 LINE Bot
`external_identity` 只屬於 Messaging API channel，兩者 subject 不可直接比較、共用或轉換。

這些資源與流程目前是程式／synth 層實作，不是 staging deployment 證據。部署前仍需 LINE Login
Channel ID、Secrets Manager secret name/ARN、BFF execution role ARN、固定 frontend HTTPS origin、
Cognito User Pool/domain/region、Email permission 與 callback 設定；不得將 Channel secret 貼入 issue、chat 或 commit。

### LINE Account Linking 與 Companion transport

Core 與 Next.js BFF 已實作 ELDER／FAMILY_MEMBER 的官方 LINE Account Linking：一個 ACTIVE LINE subject
只對應一個 Actor，且每個 Actor 只允許一個 ACTIVE LINE link。Core 只保存獨立 HMAC key 產生的
subject／nonce digest、排程推播所需的 LINE subject authenticated ciphertext、challenge lifecycle
與 `webhookEventId` receipt；LINE user ID 明文、linkToken、nonce、replyToken 與訊息逐字內容不進
資料庫或應用 log。`LINE_SUBJECT_ENCRYPTION_SECRET` 與其他 LINE／邀請 secrets 必須獨立。
每個長者一般文字事件會重新載入 live
Actor／Elder、ACTIVE Tenant 與唯一有效的 tenant-wide ELDER membership，執行
`authorize_elder`、檢查 `BASIC_VOICE` Consent，再同步呼叫 Companion。Webhook 對每個事件獨立
commit，retryable failure／stale PROCESSING receipt 最多 reclaim 三次；domain state commit 後才消耗
replyToken，因此 reply delivery 明確為 at-most-once。Batch 事件以獨立 DB session、有界 concurrency
處理，避免前段模型呼叫耗盡後段 replyToken。Web 狀態頁可查詢與解除連結，linkToken 僅
短暫存在 10 分鐘 HttpOnly Cookie。FAMILY_MEMBER 連結只用於通知，不會進入 Companion 對話。

Core 會由 `webhookEventId` 派生穩定的 Runtime `request_id`，但 Agent Runtime 尚未提供 durable
request deduplication；如果 timeout 發生在 Runtime 已完成、Core 尚未收到 response 的模糊窗口，
LINE redelivery 仍可能重複模型運算。MVP 的 `allowed_tools=[]`，因此此窗口不會重複外部 tool
side effect，但 production 在開放 tools 或要求成本級 exactly-once 前，必須先加入 Runtime
idempotency／single-flight store。

MVP 的 `LINE_IDENTITY_HMAC_KEY_VERSION` 固定為 `1`，且第一個 ACTIVE link 建立後不得原地更換
`LINE_IDENTITY_HMAC_SECRET`；正式 rotation 必須保留舊 key、執行明確 rekey／unlink migration，
並在 rolling deployment 期間維持跨版本 subject serialization。否則新 digest 無法辨識舊 link，
會破壞 LINE subject 對 Actor 的 1:1 保證。

官方流程必須把 linkToken 帶到 `/backend/line/account-link/start` 的初始 URL，Core 向 LINE 申請
linkToken 時也必須把 LINE user ID 放在官方 API path。應用程式不記錄這些值，LINE adapter 亦將
`httpx`／`httpcore` 細節 log 至少限制在 WARNING；但 staging ingress、CDN／ALB、reverse proxy、
Next.js hosting、APM 與 tracing 仍必須驗證不記錄或完整遮罩該 start route 的 query、官方 redirect
`Location`、LINE outbound URL／headers／body。未取得這項部署證據前，不得宣稱達成端到端
「不記錄」或啟用 account linking。

Core 另實作 `POST /api/v1/internal/notification-jobs/line-daily`：只接受 SYSTEM_SERVICE 提供的
`scheduled_for`、固定 job name 與 `Asia/Taipei`，且時間必須解析為 08:00；服務自行計算前一個
台北日，不接受 report content 或 LINE user ID。候選只來自當日 `PUBLISHED` DAILY Report，發送前
重查 tenant、ACTIVE FAMILY_MEMBER、Family Relationship、`FAMILY_SHARING` Consent、share scope、
LINE DAILY 08:00 Preference 與 ACTIVE encrypted destination。每筆 delivery 使用穩定 UUID／
`X-Line-Retry-Key`，最多三次，Provider 失敗只更新 Notification Delivery，不回滾 Report。
LINE 內容只含日期、已更新提示與登入 Family Web 的連結，不包含長者姓名或報表內容。

這是 feature-gated MVP，不是 staging deployment 證據：`a7c4e2d19f60`、`b8d5f3a21c74` migration
尚未獲准套用畫面中的遠端 RDS，固定 staging HTTPS origin、獨立
`LINE_IDENTITY_HMAC_SECRET`／`LINE_SUBJECT_ENCRYPTION_SECRET` 尚未注入，08:00 外部 Scheduler
也尚未部署，
先前外洩的 LINE／RDS secrets 也必須先輪替。同步 webhook 尚未具備 production SQS／DLQ、
push fallback 或正式 queue redrive；Email Notification delivery 仍未實作。
### Memory confirmation authority

目前 `POST /api/v1/elders/{elder_id}/memory-candidates/{memory_id}/confirm` 只有通過
server-side elder-self authorization 的 `ELDER_UI` 可使 Candidate 成為 `ACTIVE`。Core 由
request trace 產生 opaque `confirmation_evidence_ref`，不接受 client 提供 actor、elder 或
confirmation authority。`CAREGIVER_REVIEW` 與 `LEGAL_REPRESENTATIVE` 僅為同一 major 的
相容解析值，執行時一律以不可探測回應 fail closed，且不得留下 formal write／outbox；後續
major 才移除。`VOICE` 仍需 candidate-specific affirmative evidence，因此尚不可用。

### Voice transport

Core 已實作 Voice Session metadata、受控狀態轉移，以及 dedicated Voice Ticket issue／consume：

- `POST /api/v1/elders/{elder_id}/voice-tickets` 只從可信 `ActorContext` 推導 actor／tenant／elder，
  重驗授權與 `BASIC_VOICE` Consent，回傳最長 120 秒的 opaque Ticket；Ticket 不含可解碼的
  scope claim，也不寫入 outbox、一般 log 或 idempotency response body。
- `POST /api/v1/internal/voice-tickets/consume` 只允許 server-side `SYSTEM_SERVICE` actor，使用
  tenant-scoped row lock 重驗 Ticket、Session、Consent ID/version，且只有第一次
  `CREATED → RECORDING` 成功；到期、重播、cross-tenant／elder、撤回或取消一律 fail closed。
- `BASIC_VOICE` 撤回或被新 grant 取代時，同交易取消相關 active Voice Session，使未使用 Ticket
  立即失效。這不影響其他 Consent Purpose。

目前 `SYSTEM_SERVICE` guard 已可執行，但 ADR 0009 的 production service credential mechanism
（例如 IAM 或 mTLS）仍待 Owner 核准；因此 internal consume contract 不代表 production service
identity 已部署。WebSocket binary/audio transport、Speech Gateway、ASR Final、低信心確認與 TTS
仍屬尚未實作的 Speech workstream。`VoiceSessionV1.transport_status` 仍明確標示
`NOT_CONFIGURED`，Ticket 不得放在 URL；後續只能經 allowlisted header、WebSocket subprotocol
或第一個受保護 frame 傳送。

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
- Email Notification delivery、LINE queue／DLQ adapter 與正式 Scheduler deployment。
- 正式 Agent Handoff 與多步 Agent Tool 迴圈。
- Graph／正式 OpenSearch projection endpoint。

上述項目應留在 `docs/` 或各 Owner 的設計產物；只有已存在的 model/schema 例外必須在本文件明示，完成實作與 live verification 後才可升格為 executable contract。
