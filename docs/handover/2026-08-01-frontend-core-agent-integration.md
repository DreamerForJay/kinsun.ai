# 交接：Frontend → Core API → Agent Runtime 文字閉環

- 日期：2026-08-01
- 狀態：文字 fallback 已接通並以 Synthetic 資料完成 E2E；語音 transport 尚未實作。
- Canonical frontend：`packages/frontend/`
- 未變更：`apps/elder-web/`

## 接法

```text
Browser
  -> HttpOnly + SameSite Cookie (browser JS cannot read it)
  -> /backend/core/api/v1/* (same origin; unsafe methods require trusted Origin)
  -> Next.js BFF (Cookie -> server-side Authorization: Bearer)
  -> Core API /api/v1/* (Core contract remains bearerAuth)
       -> trusted authentication context
       -> tenant + elder authorization
       -> BASIC_VOICE consent + session state + idempotency
       -> Agent Runtime /api/v1/agent/runs (server-to-server)
       -> AgentRun + SafetyEvaluation metadata
  <- SuccessEnvelope / ErrorEnvelope
```

前端不能傳入可信的 `actor_id`、`tenant_id` 或 `actor_role`。本機 fake auth 的
Synthetic actor／tenant 由 Core 的 server-only environment 提供；正式環境仍需替換成
核准的 authenticator。Core 每次正式讀寫與 state transition 都重新檢查 live consent。
Access Token 不再存入 `localStorage`，API Client 也會刪除呼叫端提供的
`Authorization` Header；只有 BFF 能把 HttpOnly Cookie 轉成 Core Bearer Header。
Elder／Caregiver ID 只是操作目標，仍可留在 localStorage，不能當成授權依據。

`POST /backend/auth/session` 只供本機 Demo 建立 Cookie，production 會回 404。正式
Cognito 尚未串接，未實作 Refresh Token，也沒有產生假 Refresh Token；未來應由
server-side authorization-code callback 設定 Cookie。`GET` 只回報 Cookie 是否存在，
不回傳 Token，也不代表 Token 已經通過 Core 驗證。

前端每次送出文字時先建立 `VoiceSession`，再呼叫
`POST /api/v1/voice-sessions/{session_id}/companion-turns`。Core 依序推進
`CREATED → RECORDING → PROCESSING → RESPONDING → COMPLETED`，Agent Runtime 回傳的
deterministic safety 結果會記為 `AgentRun` 與 `SafetyEvaluation`。輸入與回覆不寫入
這三張稽核表；idempotency 只保存 request fingerprint 與 response body hash。

## 本機設定與啟動

先啟動 PostgreSQL 並完成 migration／Synthetic seed，再分別啟動：

```powershell
# Agent Runtime
cd services/agent-runtime
uv run uvicorn --app-dir src agent_runtime.app:app --reload --port 8001

# Core API（另開終端；DATABASE_URL 必須指向本機資料庫）
cd services/core-api
$env:FAKE_AUTH_ENABLED = "true"
$env:FAKE_AUTH_ACTOR_ID = "20000000-0000-4000-8000-000000000001"
$env:FAKE_AUTH_TENANT_ID = "10000000-0000-4000-8000-000000000001"
$env:FAKE_AUTH_ACTOR_ROLE = "ELDER"
$env:AGENT_RUNTIME_URL = "http://127.0.0.1:8001"
uv run uvicorn app.main:app --reload --port 8000

# Frontend（另開終端；server-only BFF target）
cd ../..
$env:CORE_API_INTERNAL_URL = "http://127.0.0.1:8000"
$env:FRONTEND_ORIGIN = "http://localhost:3000"
$env:NEXT_PUBLIC_CONSENT_POLICY_VERSION = "demo-consent-v1"
npm.cmd run dev --workspace @elderly-care/frontend
```

若 Windows 保留或拒絕本機 `8000`，Core 與 `CORE_API_INTERNAL_URL` 可一起改成其他
loopback port；HTTP 契約與公開 path 不變。

## 已驗證的 E2E

### HttpOnly Cookie／BFF 遷移（本次）

以臨時 Next.js dev server 實際透過 HTTP 驗證，完成後已停止該程序：

- 沒有 Cookie 呼叫 `/backend/core/health`：401，BFF fail closed。
- 開發登入：201；`Set-Cookie` 帶 `HttpOnly` 與 `SameSite=Lax`，回應 body 不含 Token。
- 帶 Cookie 呼叫 `/backend/core/health`：200，證明同源 Cookie 可通過 BFF 到 Core。
- 帶 Cookie 的跨站 POST：403，未送到 Core。
- 登出：200，session status 變成 `credential_present=false`，之後再走 BFF 為 401。
- Vitest 另直接驗證 BFF 送往 Core 的 request：只使用 Cookie 轉出的 Bearer Header，
  不轉送瀏覽器 Cookie 或瀏覽器自行提供的 Authorization Header。

當下既有 `:8000` Core process 的 protected Consent endpoint 回 401，表示該 process
沒有可用 authenticator；`:8001` Agent Runtime 也沒有回應。因此本次沒有重新宣告
protected Consent 或完整文字對話 E2E 通過，以下是 Cookie 遷移前已保存的 Synthetic
整合證據。

### 既有 Synthetic 文字閉環證據

在獨立的 `kinsun_frontend_e2e_*` Synthetic database，透過前端同源 proxy 驗證：

- 首頁、Core API、Agent Runtime health 均回 200。
- 有效 `BASIC_VOICE` consent 可建立 session 並完成一般文字對話：`ALLOW / LOW`。
- UTF-8 停藥請求：`BLOCKED / BLOCK / HIGH / HIGH_RISK_REQUEST`。
- 撤回 `BASIC_VOICE` 後建立新 session：`404 not_found / RESOURCE_NOT_FOUND`。
- `agent_run`、`safety_evaluation`、`idempotency_record` 沒有 input／reply／transcript 欄位；
  request／response 稽核值為 SHA-256 hash。

## 明確未完成

- 麥克風擷取、ASR、低信心確認、WebSocket voice session transport、TTS。
- WebSocket reusable Token query 已移除；正式語音 transport 仍需短效、一次性連線票證。
- Cognito authorization-code callback、JWT verifier 與 Refresh Token rotation。
- Bedrock、OpenSearch、Neptune；Agent Runtime 仍使用 Mock Provider。
- `packages/frontend` 其他 dashboard／family 舊 client 尚未納入本次閉環遷移。
- `apps/elder-web` 仍保留原狀，沒有宣告為 production frontend。
