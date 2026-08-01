# 需求文件：後端登入與註冊系統

## 文件狀態、已確認邊界與待核准決策

- 狀態：Proposed
- 已確認安全邊界：業務身份與授權只可來自 Core PostgreSQL `Actor`／identity／membership；瀏覽器不得持有 OAuth Token。
- 提案中的基礎設施位置：`infrastructure/`；現有 `infra/` CDK scaffold 已移除，但這不等同於核准 IaC 工具。
- 提案中的身份供應：Amazon Cognito User Pool；Google 經 Cognito federation。
- 提案中的 API authentication：Core 只接受指定 Cognito App Client 簽發的 Access Token。
- 已確認的前端信任邊界：`packages/frontend` Next.js BFF。

> **Owner／ADR Gate**：本文件不得視為 IaC 工具、AWS Region／Account／Environment、Cognito User Pool 策略、Google provider、正式 Session Store 或外部 Provider 已獲核准。Phase 0 必須先完成候選方案、trade-off、Owner 決策與必要 ADR；在此之前，下列 Cognito／CDK／AWS 資源要求都只是待核准的目標驗收條件，不授權建立或部署資源。

本規格提供正式環境可用的邀請、Google／Cognito 原生登入、pending／identity-link review、server-side session、tenant/role/care-unit context 與可稽核的身份生命週期。Cognito groups、自訂 role/tenant claims、Email、BFF request body 或使用者提供的 header 均不得授予 Core 業務權限。

## 詞彙

- **External Identity**：以正規化 `issuer + subject` 唯一識別的 Cognito identity。
- **Trusted Profile**：Core 以同一 Access Token 呼叫 Cognito UserInfo，或以 server-side `AdminGetUser` 取得並交叉驗證的 `sub`、provider、Email 與 `email_verified`。
- **BoundActorPrincipal**：`identity_id`、`actor_id`、`actor_type`、`status`；刻意不含 tenant、role 或 care unit。
- **Auth Context**：由 `tenant_id + role_code + optional care_unit_id` 唯一描述、由 Core 驗證 membership 後簽發的 server-side context。
- **Invitation Transaction**：BFF 暫存 raw invitation token 與 OAuth state/PKCE/nonce 的短效、一次性 server-side transaction；瀏覽器只持有 opaque ID。
- **Auth Session**：BFF server-side 加密保存 Access/Refresh Token 與目前 context handle 的 session；瀏覽器只持有 opaque session ID。
- **Outbox**：可靠傳送 command/notification/event 的機制，不是稽核紀錄。
- **Auth Audit Event**：獨立、immutable 的身份安全稽核紀錄。

## 需求

### R1：Canonical infrastructure、資源所有權與環境隔離

**使用者故事：** 身為平台維運者，我需要唯一且可重現的 Cognito 與 BFF session infrastructure，以避免身份分裂或設定漂移。

#### 驗收條件

1. THE System SHALL 以 `infrastructure/` 作為本功能唯一 canonical infrastructure；`infra/` 不得新增本功能資源。
2. THE System SHALL 只在 `infrastructure/lib/constructs/auth.ts` 建立或修改 Cognito User Pool、App Client、domain、identity provider 與 Cognito auth resource ownership；`infrastructure/` 其他檔案 MAY 負責 stack composition、環境 config、IAM、outputs、AuthSessionStore DynamoDB/KMS/TTL 與部署 wiring。
3. THE System SHALL 為 development、staging、production 使用不同 User Pool、domain prefix、callback/logout URL、Google credential、session table/KMS key namespace。
4. THE System SHALL 從 AWS Secrets Manager 讀取 Google Client ID/Secret，且不得將 secret 寫入 Git、CloudFormation output、client environment 或日誌。
5. THE System SHALL 輸出非敏感 User Pool ID、App Client ID、Issuer、由 Issuer 衍生或與 Issuer 交叉驗證的 JWKS URL、UserInfo URL 與 Hosted UI domain。
6. IF production 必要 URL、domain、secret、KMS/session store 或 Core Cognito 設定缺失，THEN synth/deploy/startup SHALL fail closed。
7. THE System SHALL 將 Cognito groups 視為 legacy compatibility，且不得作為 Core 授權來源。

### R2：Invitation、dedicated accept route 與一次性交易

**使用者故事：** 身為受邀者，我需要安全地攜帶邀請進入登入流程，而不讓 raw invitation token 洩漏或被重放。

#### 驗收條件

1. THE System SHALL 允許授權管理者建立 Invitation，至少包含 normalized Email、`allowed_provider`（`GOOGLE` 或 `COGNITO_NATIVE`）、`actor_type`、`tenant_id`、`role_code`、可選 `care_unit_ids` 與 expiry。
2. THE Core SHALL 只儲存高熵 invitation token 的安全 digest；明文只可在 create/resend 的一次性回應與通知傳送邊界出現。需寄送時，THE System SHALL 將 raw token KMS 加密至短效、一次性 Invitation Delivery item，outbox 只保存 opaque delivery reference，notification worker consume 後立即刪除。
3. THE BFF SHALL 提供 dedicated `GET /backend/auth/invitations/accept?token=...` route，將 raw token 立即加密存入短效 server-side OAuth transaction store，瀏覽器 cookie 只保存 opaque transaction ID。
4. THE accept route SHALL 設定 `Referrer-Policy: no-referrer`、`Cache-Control: no-store`，禁止 edge/access/application log、APM、analytics 與 query capture 記錄 `token`，並立即以 `303 See Other` 導向不含 token 的 clean URL。
5. THE BFF callback SHALL 以 conditional write 原子 consume Invitation Transaction；過期、已 consume、缺失、cookie/transaction 不符或 callback replay SHALL 拒絕且不得呼叫 invitation acceptance。
6. THE System SHALL 對 token digest 比對、Invitation row lock、identity/Actor/membership 建立與 `ACCEPTED` transition 使用單一 PostgreSQL transaction；任何失敗 SHALL 不留下部分授權。
7. THE System SHALL 只允許 `READY` 且未過期／撤銷的 Invitation 被接受，並 SHALL 驗證 trusted provider、strict verified Email、tenant、role 與 care-unit constraints。
8. THE System SHALL 對 Invitation create/resend/revoke/expire/provision/accept/conflict 寫入獨立 audit event；不得將 raw token 寫入 audit/outbox/log。

### R3：Google OAuth/OIDC callback 與 nonce

**使用者故事：** 身為 Google 使用者，我需要經 Cognito 完成防重放的登入，且 Core 不接觸 Google Token。

#### 驗收條件

1. THE System SHALL 透過 Cognito `UserPoolIdentityProviderGoogle` 整合 Google；Core 與 browser SHALL NOT 直接交換或接受 Google Token。
2. THE BFF SHALL 使用 Authorization Code flow、PKCE S256、至少 128-bit `state`、`nonce` 與一次性 server-side transaction；scope 限於 `openid email profile`。
3. THE callback SHALL 驗證 exact configured redirect URI、request Host allowlist、state、PKCE、nonce、transaction expiry/provider/returnTo 與 code single-use；callback SHALL NOT 依賴可能不存在的 `Origin` header。
4. AFTER code exchange，THE BFF SHALL 暫時驗證 Cognito ID Token 的 signature、允許 algorithm、`kid`、`iss`、`aud == COGNITO_CLIENT_ID`、`exp`、合理 `iat` 與 transaction `nonce`；成功後 SHALL 立即丟棄 ID Token，不傳 Core、不寫 session store、不持久化、不記錄。
5. IF ID Token 缺失、signature/iss/aud/exp/iat/nonce 無效、state 不符、code 重放或 exchange 失敗，THEN callback SHALL 清除/consume transaction、不得建立 session，並回傳不洩漏 provider 細節的安全錯誤。
6. THE BFF SHALL 只把 Cognito Access Token 傳給 Core；ID Token 的 Email/provider claims SHALL NOT 作為 Bootstrap 或 linking 可信輸入。
7. Google provider SHALL 保持 feature gate 關閉，直到 Core verifier/profile/bootstrap、BFF callback/session 及 staging negative tests 全部通過。

### R4：Provider provenance、Verified Email 與 account linking

**使用者故事：** 身為安全管理者，我需要知道 identity 真正來自哪個 provider，並阻止 Email-based account takeover。

#### 驗收條件

1. EVERY Bootstrap（包含既綁定、invited、pending、rejected 與 link-review identity）SHALL 透過 Core Trusted Cognito Profile Adapter 取得 profile；不得信任 BFF provider/Email body、ID Token payload 或 client hint。
2. FOR Google，adapter SHALL 以 UserInfo 與必要的 `AdminGetUser` metadata 驗證 Access Token `sub` 一致、provider provenance 明確為 `GOOGLE`、normalized Email 存在且 `email_verified` 為嚴格 boolean `true`。
3. FOR Cognito native，adapter SHALL 以 `AdminGetUser` 驗證相同 User Pool/subject、user enabled/可登入、provider provenance 明確為 `COGNITO_NATIVE`，且 Cognito `email_verified` attribute 嚴格等於 `true`；字串真值、缺值、混合/不明 provenance SHALL 拒絕。
4. Invitation acceptance SHALL 強制 `trusted_profile.provider == invitation.allowed_provider`；provider mismatch SHALL NOT fallback 到 Email matching。
5. V1 SHALL 禁止依相同 Email 自動 linking。WHEN 新 `issuer+subject` 的 verified Email 對應既有 Actor/identity，THEN THE System SHALL 建立或重用 `IDENTITY_LINK_REVIEW`，不得建立第二 Actor、不得綁定、不得授權。
6. Identity link approval SHALL 由具權限 admin 在 transaction 中完成，要求目標 Actor 明確、近期 re-auth 證據（預設不超過 10 分鐘）、provider/subject 再驗證、collision check 與 immutable audit。
7. Identity unlink SHALL 要求近期 re-auth、admin/self-service 授權政策、transaction lock 與 audit；THE System SHALL NOT unlink Actor 的最後一個 active identity。
8. IF identity 已綁其他 Actor、subject collision、provider provenance 不符或 invitation 企圖接管既有 Actor，THEN THE System SHALL 回傳一致衝突碼且不變更任何綁定。
9. Staging SHALL 有 Google 與 Cognito native trusted-profile contract tests，涵蓋 strict verified Email、sub mismatch、provider mismatch 與 linking collision。

### R5：Cognito native Invitation provisioning saga

**使用者故事：** 身為 native 受邀者，我需要由 Cognito 安全建立帳號，而跨系統失敗不會提前產生業務授權。

#### 驗收條件

1. Invitation status SHALL 僅使用 `PROVISIONING`、`READY`、`ACCEPTED`、`REVOKED`、`EXPIRED`、`FAILED`。
2. WHEN 建立 `COGNITO_NATIVE` Invitation，THE Core SHALL 在單一 DB transaction 寫入 `PROVISIONING` Invitation 與 idempotent provisioning command outbox，不得同步假裝完成 Cognito provisioning。
3. A dedicated worker SHALL 以 invitation/command idempotency key 呼叫 `AdminGetUser`／`AdminCreateUser`；重試 SHALL 不建立重複 user，且 SHALL NOT 因相同 Email 自動 link Core Actor 或既有 federated identity。
4. WHEN Cognito user 已確認符合該 Invitation，THE worker SHALL 在 DB transaction 將 Invitation 改為 `READY` 並寫 notification outbox；只有 `READY` 才可寄出/接受。
5. Cognito temporary password SHALL 只由 Cognito delivery mechanism 傳送與管理；Core、BFF、outbox payload、audit 與 application logs SHALL NOT 接收或保存 temporary/plain password。
6. Google Invitation SHALL 在 create transaction 驗證政策後直接成為 `READY`，不得預建 native user。
7. THE worker SHALL 保存非敏感 provisioning attempt、next retry、last error code、Cognito username/sub reference 與 command version，並提供 bounded retry、DLQ/`FAILED`、reconciliation 與人工重試。
8. IF Cognito 建立成功但 DB transition 失敗，THEN reconciliation SHALL 以 idempotent `AdminGetUser` 恢復至 `READY`；IF Invitation 已撤銷/過期且 user 可證明由該 Invitation 專用建立、未綁 identity且未登入，THEN compensation MAY disable/delete user，否則 SHALL disable並送人工審核，不得自動 link 或授權。
9. Native staging E2E SHALL 涵蓋 `PROVISIONING → READY → login → bootstrap → context`、重試、部分失敗 reconciliation、revoke/expire race 與 temporary-password non-disclosure。

### R6：BFF server-side Auth Session、refresh 與 logout

**使用者故事：** 身為使用者，我需要瀏覽器 session 安全續期，而 Access/Refresh Token 永不成為 browser cookie。

#### 驗收條件

1. Production browser SHALL 只以 `__Host-kinsun_session` 保存 opaque session ID；OAuth/invitation 期間 MAY 另用短效 `__Host-kinsun_oauth_tx`，但其值也只能是 opaque transaction ID。兩者均 SHALL 使用 `Secure; HttpOnly; SameSite=Lax; Path=/` 且不得設定 Domain。
2. THE BFF SHALL 以 `AuthSessionStore` server-side 加密保存 Access Token、Refresh Token、token expiry、目前 Core context handle 與 session metadata；browser cookie、local/session storage、URL、HTML 或 client log SHALL NOT 保存 raw Token/context handle。
3. `AuthSessionStore` SHALL 由 `infrastructure/` provision dedicated DynamoDB table、KMS key、TTL、最小 IAM 與 encryption context；OAuth transactions與一次性 Invitation Delivery items MAY 使用同表不同 item type。此 store SHALL NOT 成為 Actor、tenant、role 或 care-unit 授權來源。
4. Session create/rotate/delete 與 OAuth consume SHALL 使用 conditional write/version CAS；refresh SHALL 使用跨 instance lease/CAS single-flight，loser 重新讀取 winner result，不得覆寫較新 Token。
5. Cognito Access Token validity SHALL 最長 60 分鐘；encrypted access-token item 的 logical expiry SHALL 不晚於 token `exp`，refresh/session 最長期限 SHALL 不超過 Cognito refresh expiry。Logout SHALL 主動 delete item，不得依賴 DynamoDB TTL 的非即時清除。
6. Core SHALL 每次 request 重新檢查 identity、Actor 與 membership/context status；因此 DB disable/revoke SHALL 阻擋下一個 request，即使 Access Token 最多仍可在 session store 殘留至 60 分鐘。
7. Logout SHALL 只接受同源、CSRF-protected `POST /backend/auth/logout`，依適用情況呼叫 token revocation endpoint及/或 Cognito global sign-out，撤銷 Core context，刪除 server session，清 cookie，最後 `303` 至 allowlisted Cognito/app logout URL。
8. `GET /backend/auth/session` SHALL 只回最小 metadata；refresh failure SHALL 清 session並回 `401 SESSION_EXPIRED`。
9. Existing raw-token cookie/local session seam SHALL 明確限制 `APP_ENV=development` 且 production `404`；production design、proxy 與測試 SHALL 不保留 raw access/refresh-token cookie fallback。

### R7：Core Access Token 驗證與 401/503 分類

**使用者故事：** 身為安全負責人，我需要 Core 只接受完整驗證的 Cognito Access Token，並區分 credential 錯誤與 provider outage。

#### 驗收條件

1. THE Core SHALL 驗證 JWT signature、allowed algorithm、`kid`、`iss == COGNITO_ISSUER`、`exp`、合理 `iat`、`token_use == access`、非空 `sub` 與 Access Token `client_id == COGNITO_CLIENT_ID`；Access Token SHALL NOT 以 `aud` 代替 `client_id`。
2. THE BFF 驗 ID Token 時 SHALL 使用 `aud == COGNITO_CLIENT_ID`；Core SHALL NOT 接受 ID Token。
3. JWKS URL SHALL 由 canonical issuer 推導，或在使用 configured URL 前交叉驗證 scheme/host/path 屬於同一 User Pool issuer；不得信任任意 JWKS URL。
4. JWKS provider SHALL 有 timeout、response-size/key-count、TTL/stale bound 與 refresh single-flight；unknown `kid` 最多強制 refresh 一次。
5. Missing/malformed/expired token、bad signature/claims、UserInfo token rejection、UserInfo `sub` mismatch、missing/unverified Email SHALL 回 `401 AUTHENTICATION_REQUIRED`（Invitation policy error可用其業務碼）。Unknown kid 在 refresh 成功後仍未知 SHALL 回 401。
6. Timeout、DNS、TLS、Cognito/JWKS/UserInfo 5xx/429，或 provider 回傳無法安全解析/不符合協定的 malformed response，且無 safe bounded cache SHALL raise typed `AuthenticationProviderUnavailable`（typed `ServiceUnavailable` family）並回 `503 AUTH_PROVIDER_UNAVAILABLE`、`retryable=true`。Unknown-kid refresh 因 outage 且無該 key/safe cache SHALL 回 503。
7. `CognitoAuthenticator`、`get_verified_cognito_identity`、`get_bound_actor_principal` 與 `get_actor_context` SHALL 明確 re-raise `AuthenticationProviderUnavailable`/`ServiceUnavailable`，不得被 broad catch 轉為 401；其他 credential failures SHALL 正規化為 typed authentication error。
8. FastAPI exception handlers SHALL 統一產生不洩漏 Token/claim/provider細節的 401/503 envelope，並 SHALL 以 route-level tests 驗證 handler 行為。
9. Production 設定或 concrete dependencies 缺失 SHALL fail closed；`FakeAuthenticator` 只可在 development explicit triple guard 或 test dependency override 使用。

### R8：BoundActorPrincipal 與 PostgreSQL identity 授權

**使用者故事：** 身為後端開發者，我需要先安全綁定 Actor，再獨立解析 tenant context。

#### 驗收條件

1. THE System SHALL 以 unique normalized `issuer + subject` 查 `actor_identity`；不得持續以 Email 作身份 key。
2. `get_bound_actor_principal` SHALL 只回 `BoundActorPrincipal(identity_id, actor_id, actor_type, status)`，不得包含 tenant、role 或 care-unit；identity 未綁定 SHALL 回 `IDENTITY_NOT_BOUND`。
3. General protected endpoints SHALL 依序使用 verified identity、BoundActorPrincipal 與 Auth Context；Bootstrap MAY 使用尚未綁定 identity，但 SHALL 使用 Trusted Profile。
4. Actor type/status、tenant、role、care-unit 與 effective period SHALL 只從 Core PostgreSQL 取得；Token group/custom claims/request body SHALL 無效。
5. `Actor.cognito_sub` migration SHALL additive 回填並先產生 collision report；驗證雙讀與 rollback window 完成前不得移除 legacy 欄位。
6. Disabled/unlinked identity、非 ACTIVE Actor 或 invalid membership SHALL 在下一個 request 被拒絕。

### R9：Multi-tenant／role／care-unit Auth Context

**使用者故事：** 身為具有多角色或多範圍的使用者，我需要明確選擇目前授權情境。

#### 驗收條件

1. Auth Context key SHALL 是 `tenant_id + role_code + optional care_unit_id`；`auth_context_session` SHALL 保存 `role_code`。
2. `care_unit_id IS NULL` SHALL 僅代表一筆 tenant-wide membership row；care-unit-scoped row 不得被提升為 tenant-wide，亦不得以另一 role 的 row 滿足 context。
3. WHEN 一個 Actor 在單一 tenant 仍有多個 active role 或多個 tenant-wide/care-unit scope，THE System SHALL 要求選擇；只有恰好一個有效 context key時 MAY 自動選擇。
4. THE BFF SHALL 以固定 header `X-Kinsun-Auth-Context` 傳送 opaque handle；不得傳可信 raw tenant/role/care-unit header。Core SHALL 只對 handle 做 digest lookup，不接受 handle ID 或 context fields 直接查詢。
5. Context issue endpoint SHALL 以 BoundActorPrincipal 驗證 exact membership row、status/effective period與 selection；resolver SHALL 每次重新驗證 identity/Actor/membership/context binding。
6. Bootstrap SHALL NOT 直接回傳 context handle；它只回可選 context descriptors/status。BFF SHALL 再呼叫 context endpoint取得 handle，並加密保存於 AuthSessionStore。
7. Membership/identity/Actor/context revoke、expire 或變更 SHALL 使下一個 Core request 失敗；任何 authorization cache SHALL 預設停用，若日後啟用須有明確極短 TTL與同步 invalidation安全證明。

### R10：Pending、approval 與 rejected cooldown

**使用者故事：** 身為平台審核者，我需要未受邀者保持零權限，並讓核准結果立即完整落地。

#### 驗收條件

1. WHEN 未綁定、無有效 Invitation 且無 Email collision 的 identity Bootstrap，THE System SHALL 建立或重用 platform-level `PENDING` Registration Request；不得建立 tenant membership/context。
2. Uninvited Pending SHALL 進入 platform review queue，`tenant_id` SHALL 為 null；`requested_entry` 或 requested tenant SHALL 僅作不可信提示且不得決定 queue ownership或授權。
3. Admin approval SHALL 在單一 DB transaction 直接建立 Actor（或明確選定無 collision 的 Actor）、actor_identity、tenant-wide/care-unit memberships、request `APPROVED` 與 audit；下一次 Bootstrap SHALL 只 resolve 現有綁定，不得再次 finalize。
4. Reject SHALL 記錄 reason/audit 並設定 configurable cooldown（預設 30 日）；cooldown 內 Bootstrap SHALL 回 `403 REGISTRATION_REJECTED`，不得自動 reopen或建立新 request。期滿後 MAY 依政策建立新 `PENDING`。
5. Pending/rejected Bootstrap SHALL 仍每次取得 Trusted Profile；profile invalid SHALL 不建立或更新 request。
6. `PENDING` SHALL 以 HTTP 202 正常 Bootstrap response 表示，不得包裝為 `ErrorEnvelope`。

### R11：API routes、契約與唯一狀態／錯誤矩陣

**使用者故事：** 身為前後端開發者，我需要單一、不互相矛盾的 API 行為。

#### 驗收條件

1. BFF SHALL 提供 invitation accept、login、callback、session、refresh、context selection 與 POST logout routes；Core SHALL 提供 bootstrap、context、Invitation、Registration Review、Identity Link Review/link/unlink 與既有 `/api/v1/me`。
2. OpenAPI skeleton（paths、security boundary、schemas、status/error matrix）SHALL 在實作 routes 前建立；實作後 SHALL 通過 static/live contract checks。
3. Admin routes SHALL 只使用 Core membership/context authorization，遵循 tenant/platform scope、idempotency、pagination、optimistic concurrency與 non-disclosure。
4. 所有 BFF/Core response SHALL 遵循本文件唯一矩陣；`PENDING 202` 是正常 response，其餘錯誤使用既有 `ErrorEnvelope`：

| HTTP | code/status | 使用情境 |
|---:|---|---|
| 200 | `ACTIVE`／`TENANT_CONTEXT_REQUIRED`／`IDENTITY_LINK_REVIEW` | Bootstrap 正常狀態；不回 context handle |
| 202 | `PENDING` | 正常 pending Bootstrap response，不是 error |
| 303 | — | invitation clean redirect、callback完成與 POST logout |
| 400 | `INVITATION_INVALID` | token 格式/transaction/provider/email不符等不可安全細分的無效邀請 |
| 401 | `AUTHENTICATION_REQUIRED` | 缺失、無效、過期 credential/profile |
| 401 | `SESSION_EXPIRED` | BFF session缺失、過期或 refresh失敗 |
| 403 | `ACCOUNT_DISABLED` | 已綁 identity/Actor被停用 |
| 403 | `REGISTRATION_REJECTED` | rejected cooldown尚未結束；不自動reopen |
| 403 | `FORBIDDEN` | 已驗證但缺少操作權限 |
| 409 | `IDENTITY_NOT_BOUND` | 一般 protected API identity 尚未綁 Actor |
| 409 | `IDENTITY_ALREADY_BOUND` | subject 已綁其他 Actor或 linking collision |
| 409 | `INVITATION_CONFLICT` | Invitation row/Actor/membership狀態衝突 |
| 409 | `TENANT_CONTEXT_REQUIRED` | 無唯一 context 或尚未選擇 |
| 410 | `INVITATION_EXPIRED` | 已過期／撤銷且政策允許揭露的 invite |
| 429 | `RATE_LIMITED` | auth/invitation/admin abuse protection |
| 503 | `AUTH_PROVIDER_UNAVAILABLE` | Cognito/JWKS/UserInfo unavailable，retryable |

5. Public-facing flow MAY 將可造成 enumeration 的細項正規化為 `INVITATION_INVALID`/`AUTHENTICATION_REQUIRED`；internal audit SHALL 保存精確 reason code。

### R12：獨立稽核、outbox、隱私與濫用防護

**使用者故事：** 身為隱私與安全負責人，我需要不可變稽核且不混淆可靠傳送機制。

#### 驗收條件

1. THE System SHALL 建立獨立 `auth_audit_event` immutable table/audit sink，至少含 event ID/type、occurred_at、result/reason、trace ID、subject/identity/Actor internal ID、nullable `tenant_id` 與最小 metadata；application role SHALL 不得 update/delete。
2. Audit retention/access policy SHALL 由環境設定與法規政策明定，預設線上保存 400 日後受控封存/刪除；只有 security/compliance role 可查詢，tenant-scoped admin不得讀 platform/global事件。
3. Outbox SHALL 只負責可靠 command/notification/event delivery；outbox delivery/deletion SHALL NOT 刪除、取代或被視為 audit event。
4. Invitation、provisioning、bootstrap、pending review、identity link/unlink、context issue/revoke、logout-all、account disable SHALL 各自寫 audit event。
5. Logs/audit/outbox/metrics SHALL NOT 包含 JWT、OAuth code、PKCE verifier、client secret、raw invitation token、temporary password或完整 Authorization header；query/edge redaction SHALL 覆蓋 invitation accept route。
6. Login/callback/bootstrap/invitation/refresh/recovery/link/admin routes SHALL 有 rate limit或managed protection；`returnTo`、callback host/redirect與logout redirect SHALL 使用 exact allowlist。

### R13：可觀測性、營運與 rollout

**使用者故事：** 身為維運者，我需要在不暴露敏感資訊下定位故障並安全漸進啟用。

#### 驗收條件

1. THE System SHALL 提供 login/callback/ID-token validation/refresh/JWKS refresh/profile/bootstrap/provisioning/context/authorization denial metrics，不得以 Token或Email作 label/correlation key。
2. THE System SHALL 以 trace ID 串接 BFF、Core、worker與AWS logs，並對 Cognito/JWKS outage、callback/refresh spike、provisioning DLQ、pending/link-review backlog與invitation abuse告警。
3. Runbook SHALL 涵蓋 Google/client/key rotation、session KMS/table incident、Cognito outage、native reconciliation/compensation、disable/logout-all與 rollback。
4. Rollout SHALL 依序完成 additive schema、session infrastructure、Core verifier/profile/principal/context、BFF session/callback、native worker與 staging contracts；在上述依賴未 ready 前 SHALL 不啟用 Google provider/public entry。
5. Rollback SHALL 關閉入口/provider feature gate並維持 Core fail closed；不得回退到 production fake auth或 raw-token cookie。

### R14：測試與完成定義

**使用者故事：** 身為交付負責人，我需要可重現證據證明所有信任邊界正確。

#### 驗收條件

1. Core tests SHALL 涵蓋 Access Token `client_id`、ID-vs-access rejection、issuer/JWKS derivation、signature/alg/kid/exp/iat、unknown-kid 401與 outage 503、safe cache及 FastAPI 401/503 handlers。
2. BFF tests SHALL 涵蓋 state/PKCE/nonce、ID Token signature/iss/aud/exp/iat/nonce negative cases、callback Host/redirect allowlist且無 Origin、transaction atomic consume/replay、303 clean URL、no-referrer/no-store及 edge/query redaction。
3. Session tests SHALL 涵蓋 opaque cookies、KMS-encrypted storage、CAS cross-instance refresh、TTL/delete、CSRF POST logout、revoke/global sign-out、context cleanup及 production raw-cookie seam 404。
4. Domain integration tests SHALL 涵蓋 Invitation lifecycle/saga/reconciliation、allowed provider、strict verified Email、Bootstrap idempotency、identity collision/link/unlink/last-identity guard、pending approval transaction/rejected cooldown與 audit/outbox separation。
5. Context tests SHALL 涵蓋 single/multi tenant、同 tenant多 role/scope、tenant-wide null規則、fixed context header/digest lookup、disabled Actor與membership expiry/revoke。
6. Staging E2E SHALL 至少涵蓋 Google invited flow、Google pending/approval、native `PROVISIONING→READY` flow、provider/profile contracts、`/api/v1/me`、logout及偽造 role/tenant/group失敗。
7. Completion SHALL 要求 infrastructure synth/typecheck/assertions、Core lint/tests、frontend typecheck/tests、worker tests、OpenAPI static/live checks、migration tests與 security/privacy review全數通過。

## 非目標

- V1 不實作 LINE federation。
- V1 不做 Email-based automatic account linking。
- Cognito groups 不取代 Core Actor/membership。
- Core 不提供 Email/password login endpoint，亦不處理 plaintext/temporary password。
- 未核准公開使用者不會自動成為任何 tenant角色。
- Legacy TypeScript Lambda authorizer移除另立計畫；本規格只要求與新 Core邊界隔離。
