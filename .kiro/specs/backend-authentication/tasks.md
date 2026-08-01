# 實作任務：後端登入與註冊系統

> 狀態：Proposed。若 Owner 核准本提案，canonical infrastructure 為`infrastructure/`，Cognito resource ownership只在`infrastructure/lib/constructs/auth.ts`；其他`infrastructure/`檔案可做stack/config/IAM/AuthSessionStore wiring。
>
> 執行原則：嚴格依依賴順序；Phase 0 的 Owner／ADR Gate 核准前不得開始資源或產品實作。每個Phase validation gate通過後才能進下一Phase。Google provider/public entry全程feature-gated，直到Staging Gate通過。任務中的測試是完成條件，不代表規格階段已修改程式碼。

## Phase 0：Owner／ADR Gate、安全基線與部署輸入

- [ ] 0.0 核准技術與部署決策
  - 比較 IaC 工具候選與 trade-off，確認是否採用現有`infrastructure/` AWS CDK workspace，並以 Owner 決策／ADR 記錄。
  - 決定 AWS Region、Account／Environment策略、正式 Cognito User Pool／Google federation策略，以及 AuthSessionStore候選方案。
  - 若核准方案不同於本提案，先同步修訂 requirements、design與tasks；不得直接沿用後續Phase。
  - Requirements：文件狀態與 Owner／ADR Gate

- [ ] 0.1 在核准方案下鎖定canonical ownership與legacy邊界
  - 記錄`infrastructure/`唯一canonical、`auth.ts`擁有Cognito resources、`infra/`不新增auth。
  - 盤點現有User Pool/users與retain/import/rollback策略，不重建production pool。
  - 隔離legacy Lambda authorizer/Cognito groups；Core不讀其role。
  - Requirements：R1、R13

- [ ] 0.2 收集exact environment設定
  - 確認dev/staging/prod frontend origins、callback/logout/Host allowlists、Cognito domain prefix。
  - 建立Google OAuth Web Client，redirect至Cognito`/oauth2/idpresponse`；Secrets Manager保存credential。
  - 確認notification sender、ADMIN MFA、support/security/compliance owners。
  - Requirements：R1、R3、R13

- [ ] 0.3 核准身份與retention政策
  - 採用transaction 10分鐘、recent re-auth 10分鐘、Access Token 60分鐘上限、refresh/session 30日上限、rejected cooldown 30日、audit online retention 400日預設。
  - 明定platform pending/link-review審核者、tenant invitation權限、unlink/self-service與compensation approval。
  - 明定V1禁止Email automatic linking與`CONTENT_MANAGER`不自帶identity admin。
  - Requirements：R4、R10、R12

- [ ] 0.V Validation gate
  - Owner決策與必要ADR已完成；IaC、Region、Account／Environment、身份供應與Session Store沒有未標示的隱含選型。
  - Security/operations sign-off deployment inputs與ownership矩陣。
  - 確認Google feature gate預設false且production缺設定fail closed。

## Phase 1：Additive PostgreSQL、audit與outbox基礎

- [ ] 1.1 建立additive Alembic migration
  - 建立`actor_identity`。
  - 建立`auth_invitation`、invitation-care-unit join；status限定`PROVISIONING/READY/ACCEPTED/REVOKED/EXPIRED/FAILED`，加入provisioning/retry/reconciliation欄位。
  - 建立`registration_request`（platform pending、`rejected_until`）與`identity_link_review`。
  - 建立`auth_context_session`，包含`role_code`與handle digest。
  - 建立獨立append-only`auth_audit_event`；建立/沿用command/notification outbox但不得等同audit。
  - 加入unique/FK/check/partial index/version/expiry constraints；不drop`actor.cognito_sub`。
  - Requirements：R2、R4、R5、R8、R9、R10、R12

- [ ] 1.2 新增ORM models、enums與redaction
  - 遵循`eldercare_ai`、UUID、timezone/BaseModel慣例。
  - `AuthInvitation`只映射digest，不持久化raw token/password。
  - Audit model不提供application update/delete repository；metadata allowlist與nullable tenant。
  - repr/serialization排除digest、provider raw response與sensitive fields。
  - Requirements：R2、R5、R12

- [ ] 1.3 新增repositories與transaction primitives
  - Identity lookup/lock by normalized`issuer+subject`；Actor active identities count。
  - Invitation create/lock/status/retry/reconcile；registration/link-review lock/review/cooldown。
  - Context issue/digest resolve/revoke，exact`tenant+role+care-unit`membership query。
  - Audit append-only repository與分離outbox repository。
  - Requirements：R4、R5、R8、R9、R12

- [ ] 1.4 回填legacy`Actor.cognito_sub`
  - 先產生duplicate/collision dry-run report，衝突fail closed人工處理。
  - 無衝突才用canonical issuer回填`actor_identity`；建立雙讀metric、rollback/reconciliation。
  - 不在本Phase移除欄位。
  - Requirements：R8

- [ ] 1.V Validation gate
  - Alembic upgrade/downgrade（僅additive可逆部分）、schema constraint tests。
  - Repository concurrency/row-lock/rollback、audit immutability與outbox separation tests。
  - Migration collision與sensitive serialization tests。

## Phase 2：AuthSessionStore與canonical Cognito（Google仍關閉）

- [ ] 2.1 Provision dedicated AuthSessionStore
  - 在`infrastructure/`建立dedicated DynamoDB、customer-managed KMS、TTL、PITR與environment namespace。
  - 定義`AUTH_SESSION/OAUTH_TRANSACTION/INVITATION_DELIVERY`item type、logical expiry、encryption context與最小BFF/notification-worker IAM。
  - Invitation Delivery只保存KMS加密短效raw token；outbox只含opaque reference，worker consume後立即刪除。
  - 明定TTL只cleanup；consume/logout必須conditional delete。
  - Requirements：R1、R6

- [ ] 2.2 擴充`infrastructure/lib/constructs/auth.ts`
  - 增加environment callbacks/logout/domain/Google secret與`enableGoogle=false`。
  - Code grant/PKCE、`openid email profile`、Access Token最多60分鐘、native Cognito login。
  - 保持retain/environment naming；production缺必要設定synth fail closed。
  - Requirements：R1、R3、R6

- [ ] 2.3 定義Google IdP但保持feature gate關閉
  - Secrets Manager dynamic reference、minimal attribute mapping、`UserPoolIdentityProviderGoogle`。
  - 未通過Phase 9前不得在有效App Client入口/production UI啟用Google。
  - Core不讀groups/custom role claims。
  - Requirements：R1、R3

- [ ] 2.4 Wiring、IAM與outputs
  - 輸出User Pool ID/Client ID/Issuer/UserInfo/Hosted UI；JWKS由issuer衍生或交叉驗證。
  - Core profile adapter/worker IAM限定canonical User Pool必要Admin actions。
  - Edge/access/APM redaction設定覆蓋invitation `token` query、cookies、code與Authorization。
  - Requirements：R1、R2、R5、R12

- [ ] 2.V Validation gate
  - Infrastructure typecheck、CDK assertions、synth。
  - 驗Google gate=false；template/output無secret literal。
  - DynamoDB/KMS/TTL/IAM、Access Token TTL、callback/logout與production fail-closed assertions。

## Phase 3：OpenAPI skeleton與typed error foundation（先於routes）

- [ ] 3.1 建立OpenAPI contract skeleton
  - 先定義bootstrap/context/invitation/registration/link/unlink paths與security boundary，尚未掛route。
  - 定義Bootstrap正常`200/202`schemas；PENDING 202不是ErrorEnvelope，Bootstrap不回context handle。
  - 定義唯一status/error matrix：`IDENTITY_NOT_BOUND`、`INVITATION_INVALID/EXPIRED/CONFLICT`、`IDENTITY_ALREADY_BOUND`、`REGISTRATION_REJECTED`、`SESSION_EXPIRED`、`AUTH_PROVIDER_UNAVAILABLE`等。
  - Requirements：R11

- [ ] 3.2 新增typed exception與FastAPI handlers
  - 建立`ServiceUnavailable`/`AuthenticationProviderUnavailable`與credential authentication errors。
  - 401/503 ErrorEnvelope不洩漏provider/token細節；503標`retryable=true`。
  - 先寫route-level handler tests，確認broad catch不得吞outage。
  - Requirements：R7、R11

- [ ] 3.3 建立共享domain DTO
  - `VerifiedCognitoIdentity`、`TrustedCognitoProfile`、`BoundActorPrincipal(identity_id, actor_id, actor_type,status)`。
  - Principal明確不含tenant/role/care-unit。
  - 定義context descriptor/key與fixed header`X-Kinsun-Auth-Context`。
  - Requirements：R4、R8、R9

- [ ] 3.V Validation gate
  - OpenAPI lint/static checks通過且與唯一matrix一致。
  - FastAPI 401/503 handler tests及DTO invariant tests通過。

## Phase 4：Core Cognito verifier與Trusted Profile（尚不啟用production authenticator）

- [ ] 4.1 加入pinned JWT/HTTP dependencies
  - 精確版本、license/supply-chain/transitive review；不手寫crypto。
  - Requirements：R7

- [ ] 4.2 擴充Settings與startup validation
  - Issuer/client ID/User Pool/UserInfo/JWKS/cache TTL/stale bound/HTTP limits。
  - JWKS由issuer衍生或scheme/host/path/User Pool交叉驗證。
  - Production partial/missing config fail closed；secret設定redaction。
  - Requirements：R1、R7

- [ ] 4.3 實作bounded JWKS provider
  - Timeout、size/key-count/kty/alg限制、TTL/bounded stale、refresh single-flight。
  - Unknown kid最多refresh一次；成功仍未知=401，outage且無key/safe cache=503。
  - Requirements：R7

- [ ] 4.4 實作Access Token verifier
  - 驗signature/alg/kid/`iss`/`exp`/bounded`iat`/`token_use=access`/`sub`與`client_id == COGNITO_CLIENT_ID`。
  - 明確拒絕ID Token與以`aud`替代access client_id。
  - Credential錯誤typed 401；provider outage保留typed 503。
  - Requirements：R7

- [ ] 4.5 實作Trusted Cognito Profile Adapter
  - 所有Bootstrap可用的server-side UserInfo/AdminGetUser adapter。
  - Google：sub match、provider provenance、`email_verified`嚴格JSON boolean true。
  - Native：AdminGetUser Pool/subject/enabled/native provenance、attribute嚴格`true`；混合/不明provider fail closed。
  - Token rejection/sub mismatch/unverified Email=401；timeout/DNS/5xx/429/malformed provider response且無safe cache=503。
  - 不接受BFF Email/provider/ID Token claims。
  - Requirements：R4、R7

- [ ] 4.6 修正exception propagation
  - `CognitoAuthenticator`、verified identity dependency明確re-raise`AuthenticationProviderUnavailable/ServiceUnavailable`。
  - Log/metric不含token/claims/profile PII。
  - 此時仍不接production business routes。
  - Requirements：R7

- [ ] 4.V Validation gate
  - JWT/JWKS完整positive/negative/cache/rotation/stampede tests。
  - Unknown-kid兩分支、UserInfo/AdminGetUser 401/503分類及FastAPI handler integration tests。
  - Google/native strict profile contract unit tests；Core lint/unit tests。
  - 驗production authenticator尚未activation。

## Phase 5：Principal、Auth Context resolver與production activation

- [ ] 5.1 實作三層dependencies
  - `get_verified_cognito_identity`允許unbound。
  - `get_bound_actor_principal`只從identity/Actor回四欄；unbound=`IDENTITY_NOT_BOUND`。
  - `get_actor_context`解析fixed header opaque handle；typed outage明確re-raise。
  - Requirements：R7、R8

- [ ] 5.2 實作PostgreSQL principal/context resolver
  - `issuer+subject` lookup；Actor/identity ACTIVE。
  - Handle只做digest lookup；拒絕raw tenant/role/care-unit header/claims。
  - 每request驗exact membership status/effective period；care_unit null只有tenant-wide row。
  - Requirements：R8、R9

- [ ] 5.3 實作Auth Context service
  - Context key=`tenant_id+role_code+optional care_unit_id`。
  - 單tenant多role/scope仍要求選；恰一key才可auto-select。
  - Issue高熵handle、DB只存digest；revoke/expire/identity/Actor/membership變更立即失效。
  - Requirements：R9

- [ ] 5.4 啟用production authenticator composition
  - 只有verifier、profile adapter、principal/context resolver都存在後，才實作`_resolve_production_authenticator`並保護既有business routes。
  - Production no-config/partial dependency fail closed；fake auth保持development triple guard/test override。
  - Requirements：R7、R8

- [ ] 5.V Validation gate
  - Unbound/disabled/unlinked、membership expiry/revoke與DB disable-next-request tests。
  - Single/multi tenant、同tenant多role/scope、tenant-wide null、header/digest/collision tests。
  - Token group/custom role/tenant claims無法改授權；production activation/no-fake tests。

## Phase 6：Bootstrap、Invitation、Pending與Identity linking services

- [ ] 6.1 實作Invitation core service
  - CSPRNG token/digest、READY-only acceptance、expiry/resend rotation/revoke/row lock。
  - Exact trusted provider、strict verified Email、tenant/role/care-unit constraints。
  - Google create直接READY；native create交易寫PROVISIONING+command outbox+audit。
  - Raw token只create/resend一次性回應與KMS加密短效Invitation Delivery item；notification outbox只存opaque reference，logs/audit/outbox禁存raw value。
  - Requirements：R2、R4、R5

- [ ] 6.2 實作AuthBootstrapService
  - 每次（含existing/pending/rejected/link-review）取得Trusted Profile。
  - READY invitation接受在單一transaction建立/綁Actor、identity、memberships、ACCEPTED與audit。
  - 無invite/collision時upsert platform PENDING，tenant null；requested tenant/entry不授權。
  - Bootstrap只回status/context descriptors，不回handle。
  - Requirements：R2、R4、R8、R9、R10

- [ ] 6.3 實作Pending review
  - Platform queue list；tenant admin不能取得uninvited queue ownership。
  - Approval transaction直接建立Actor/identity/exact memberships/APPROVED/audit；下次Bootstrap只resolve。
  - Reject設定預設30日cooldown；期間不得auto-reopen。
  - Requirements：R10

- [ ] 6.4 實作Identity Link Review/link/unlink
  - 相同Email的新subject建立`IDENTITY_LINK_REVIEW`，不auto-link/不建第二Actor/不授權。
  - Approval要求explicit Actor、10分鐘內reauth、Trusted Profile再驗、row locks/collision/audit。
  - Unlink要求reauth、撤銷contexts/sessions；不可unlink最後一個active identity。
  - Requirements：R4

- [ ] 6.5 建立Core routes（依Phase 3 skeleton）
  - Bootstrap、context issue/revoke、Invitation CRUD/resend/revoke、Registration approve/reject、Link Review/link/unlink。
  - Admin routes使用Core context authorization、idempotency/pagination/If-Match/non-disclosure。
  - 實作與OpenAPI live contract同步。
  - Requirements：R9、R10、R11

- [ ] 6.V Validation gate
  - Invite valid/reuse/expire/revoke/provider/email mismatch/race/rollback tests。
  - Bootstrap idempotency、no-handle response、platform pending、approval finalize、cooldown tests。
  - Auto-link禁止、identity collision、reauth、last-active guard、audit completeness tests。
  - OpenAPI static/live contract與唯一matrix tests。

## Phase 7：Native provisioning worker與notifications

- [ ] 7.1 實作Cognito administration gateway
  - `AdminGetUser/AdminCreateUser/AdminDisableUser`等最小操作，限定canonical Pool。
  - Idempotency以invitation/command reference；同Email不得觸發Core link。
  - 不設定、讀取、代理或記錄temporary password；由Cognito delivery。
  - Requirements：R5

- [ ] 7.2 實作provisioning worker
  - Claim PROVISIONING command、bounded retry/backoff/attempt/next-at/error/version。
  - Idempotent Get/Create成功後DB transaction寫READY+notification outbox+audit。
  - Retry exhausted轉FAILED/DLQ；FAILED不可接受。
  - Requirements：R5、R12

- [ ] 7.3 實作reconciliation/compensation
  - Cognito成功DB失敗時AdminGetUser恢復READY。
  - Revoke/expire後，只有專用建立、未登入/未綁可delete；其他disable+manual review。
  - Reconciliation永不依Email自動link或建立membership。
  - Requirements：R5

- [ ] 7.4 實作notification worker
  - READY後才寄app invite/readiness；native temporary password仍由Cognito送。
  - Notification outbox retry不改audit；resend輪替token使舊token立即失效。
  - Requirements：R2、R5、R12

- [ ] 7.V Validation gate
  - AdminGetUser/Create idempotency、PROVISIONING→READY、Google no-precreate。
  - Cognito-success/DB-failure reconcile、retry/FAILED/DLQ、revoke compensation race。
  - Temporary password/raw token non-disclosure與audit/outbox separation tests。

## Phase 8：BFF invitation/OAuth transaction、server session與callback

- [ ] 8.1 實作AuthSessionStore adapter
  - KMS envelope encryption、logical expiry、item type/version CAS、consistent read與conditional delete。
  - Session payload存Access/Refresh Token、expiry、server-side context handle；browser只opaque session ID。
  - Requirements：R6

- [ ] 8.2 實作dedicated invitation accept route
  - `GET /backend/auth/invitations/accept?token=...`立即加密存raw token，cookie只有opaque tx ID。
  - `no-store`、`Referrer-Policy: no-referrer`、edge/query/APM redaction，立即303 clean URL。
  - Expiry/tamper/replay與conditional consume tests。
  - Requirements：R2、R12

- [ ] 8.3 實作login start
  - state/nonce/PKCE S256 CSPRNG，短效server transaction綁provider/returnTo/Host/callback。
  - Google使用Cognito identity provider但入口仍受feature gate；raw invitation不進state/URL。
  - Requirements：R2、R3

- [ ] 8.4 實作callback與ID Token暫時驗證
  - 不依賴Origin；驗exact redirect URI/Host allowlist/state/PKCE/transaction/code single-use。
  - Code exchange後驗ID Token signature/alg/kid/iss/`aud`/exp/iat/nonce；成功立即丟棄，不傳Core/不持久化。
  - Atomic consume invitation transaction，建立opaque server session，呼叫Bootstrap。
  - ACTIVE時另呼context endpoint；PENDING/link-review/context selection使用allowlisted303。
  - Requirements：R2、R3、R6、R9

- [ ] 8.5 實作CAS refresh manager與Core proxy
  - 跨instance lease/version CAS single-flight；loser重讀winner，terminal失敗刪session。
  - Proxy只由store取Access Token；固定`X-Kinsun-Auth-Context`傳server-side handle。
  - 不保留production raw-token cookie fallback；retry最多一次。
  - Requirements：R6、R9

- [ ] 8.6 實作session/context/POST logout routes
  - `GET /session`最小metadata、POST context把handle加密存session。
  - `POST /logout`same-origin/CSRF；revoke/global sign-out適用時執行，撤銷Core context、delete session/cookies後303。
  - Local raw-token seam只development explicit flag，production 404。
  - Requirements：R6、R11

- [ ] 8.V Validation gate
  - Frontend typecheck/unit/integration tests。
  - ID Token signature/iss/aud/exp/iat/nonce全部negative tests；state/PKCE/replay/Host且callback無Origin tests。
  - Opaque cookie/KMS storage、no-store/no-referrer/303/redaction、CAS跨instance refresh tests。
  - CSRF POST logout/revoke/context cleanup；production raw-cookie/local seam 404。

## Phase 9：Staging contracts、E2E與Google enablement gate

- [ ] 9.1 部署staging additive stack
  - DB→session infrastructure/Cognito gate-off→Core→worker→BFF。
  - Production authenticator已在resolver後啟用；先以native/internal flow dark validate，不開Google public entry。
  - Requirements：R13、R14

- [ ] 9.2 執行provider/profile staging contracts
  - Google UserInfo/AdminGetUser provenance、strict boolean true、sub/provider mismatch。
  - Native AdminGetUser enabled/native provenance、strict email_verified、mixed provider fail closed。
  - 401 credential與503 timeout/DNS/5xx/429/malformed provider response實際handler contract。
  - Requirements：R4、R7、R14

- [ ] 9.3 執行native staging E2E
  - PROVISIONING→READY→notification/Cognito temporary password→login→bootstrap→context→`/me`→logout。
  - 部分失敗reconciliation、retry、revoke/expire race、password non-disclosure。
  - Requirements：R5、R14

- [ ] 9.4 在staging啟用Google並執行E2E
  - READY invite→dedicated accept→Google/Cognito callback→bootstrap→context endpoint→`/me`→POST logout。
  - Uninvited→PENDING platform queue→approval transaction→next bootstrap resolve。
  - ID Token/state/nonce negative、identity link review、disabled Actor、membership revoke。
  - Requirements：R3、R4、R10、R14

- [ ] 9.5 執行安全負面測試
  - 偽造groups/custom role/tenant/care-unit、raw context header、aud/client_id混淆。
  - Invitation brute force/reuse/query leakage、OAuth replay/open redirect/CSRF/session fixation。
  - Cross-tenant admin、auto-link企圖、unlink最後identity、native compensation safety。
  - Requirements：R7、R9、R12、R14

- [ ] 9.V Validation gate
  - Infrastructure synth/typecheck/assertions；Core lint/full tests；worker tests；frontend typecheck/full tests。
  - OpenAPI static/live checks、migration tests、security/privacy/audit access review、alerts/runbook演練。
  - 只有全部通過才允許production Google feature gate變更。

## Phase 10：Production rollout與營運

- [ ] 10.1 Production readiness review
  - Exact allowlists/secrets/KMS/IAM/diff reviewed；rollback與session invalidation演練。
  - Cognito/JWKS/UserInfo outage、native DLQ/reconciliation、audit retention/access與support ownership ready。
  - 確認Core fail closed、無fake/raw-token production fallback。
  - Requirements：R13、R14

- [ ] 10.2 漸進啟用Google/public入口
  - 先internal cohort，再受邀cohort，再public login；每階段獨立feature gate approval。
  - 監控callback/ID-token/refresh/JWKS/profile/bootstrap/provisioning/pending/link/context/denial metrics。
  - 異常時關入口/Google provider並reconcile in-flight，不繞過Core auth。
  - Requirements：R13

- [ ] 10.3 驗證disable/logout與retention
  - DB disable/revoke在下一Core request生效；session token最多60分鐘但不授權。
  - POST logout主動delete（不等TTL）、audit append-only與400日retention job權限正確。
  - Requirements：R6、R12

- [ ] 10.V Validation gate
  - Production smoke tests與告警觀察窗口通過。
  - Security/operations正式簽核；記錄已啟用cohort與rollback point。

## Phase 11：後續清理（不阻塞V1，但須另排程）

- [ ] 11.1 移除`Actor.cognito_sub`
  - 僅在回填完成、collision清零、fallback metric歸零與rollback window結束後另立migration。

- [ ] 11.2 淘汰development raw-token seam
  - 保留test dependency override；本地改明確fixture/local Cognito strategy。

- [ ] 11.3 統一legacy TypeScript authorizer
  - 另立migration spec將DynamoDB/Cognito groups授權移入Core PostgreSQL或完全隔離。

- [ ] 11.4 評估LINE federation
  - 沿用provider-neutral trusted profile/link-review/BFF flow，不複製role/membership邏輯。
