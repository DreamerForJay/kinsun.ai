# ADR 0009：Gate 1 Synthetic Profile 與服務信任邊界

- 狀態：Accepted for Gate 1 synthetic implementation；production provider 與 credential mechanism 仍待核准
- 日期：2026-08-02
- Owner：Project Owner
- Expiry：2026-09-30 或 Gate 1 release evidence review，以較早者為準
- 決策依據：Project Owner 指示依 canonical Gate 1 計畫開始實作
- 相關：[ADR 0004](0004-agent-runtime-into-monorepo.md)、
  [ADR 0007](0007-canonical-backend-and-aws-deployment-authority.md)、
  [Gate 1 requirements](../../.kiro/specs/gate-1-agent-vertical-slice/requirements.md)、
  [Gate 1 design](../../.kiro/specs/gate-1-agent-vertical-slice/design.md)

## 背景

Canonical Gate 1 需要先證明下列行為可安全、可重跑：

- Browser → BFF → Core → Agent Runtime 是唯一一般互動主線。
- Core 以可信 server-side context 重新驗證 actor、tenant、elder、assignment、consent 與 state。
- 語音低信心、撤回、停止與失敗在任何 Candidate 或正式寫入前生效。
- Agent 只能提出 Event／Memory Candidate；人工 Gate 才能產生正式狀態。
- 正式狀態與 outbox 同交易，projection 可重建且不得讓刪除資料復活。

Production ASR／TTS、Bedrock model／Guardrails、Graph provider 與 service credential mechanism 尚未完成
Owner 選型。若等待所有 production provider 才開始，會讓 Domain、安全與 failure-path 測試無法前進；
若直接把 Mock 或 staging adapter 當成 production，則會製造錯誤完成度。

本 ADR 只核准 **Gate 1 synthetic implementation 與測試 profile**。它不核准 production provider、
production quality／latency、data region、成本上限或 application deployment。

## 決策

### 1. AgentRun 只有 Core 一個正式 authority

- Core 在呼叫 Agent Runtime 前建立唯一 `agent_run_id`，保存可信 session、tenant、elder、actor、
  consent、policy 與版本關聯。
- Agent Runtime 必須重用 Core 傳入的 `agent_run_id`，不得建立第二筆正式 AgentRun。
- Agent Runtime 回傳結果後，由 Core 完成同一筆 AgentRun；dependency failure、timeout、Safety block
  與取消也由 Core 記錄 bounded result status。
- Tool Command 必須攜帶該 `agent_run_id`、correlation／causation ID 與 idempotency key；Core 重新驗證後
  才能執行。
- 現有 Runtime register→Tool→complete 隔離測試只保留為 baseline，不是 canonical authority。

### 2. Service identity 採 provider-neutral 驗證 contract

Core↔Agent 與 Agent↔Core private call 必須先轉成可信 `ServicePrincipal`。Credential 至少包含並驗證：

- issuer、subject service、audience；
- issued-at、expiry，Gate 1 上限 60 秒；
- credential ID／nonce 與 request correlation；
- 完整性簽章；
- endpoint allowlist 與 service-to-service direction。

其他規則：

- Browser Bearer token、Cookie、query credential 或模型輸出不得成為 `ServicePrincipal`。
- Agent Runtime 必須拒絕 browser direct access、缺少 credential、錯誤 audience、過期與 replay。
- Core Tool endpoint 只接受核准的 Agent Runtime principal，不接受 caller 自稱 `SYSTEM_SERVICE`。
- Local／test profile 可使用 deterministic signed test credential，但 key 只能由 fixture 注入，
  不得進版控、log、trace 或 response。
- 非 test profile 若沒有正式 verifier，必須 fail closed。
- Production 採 IAM、mTLS 或其他 mechanism 仍待 Owner 核准；本 ADR 不替代該決策。

### 3. Tool scope 只能由 Core 推導

- Core 根據 trusted actor context、tenant、elder、assignment、Consent Purpose、session state、policy
  與 resource state 建立 allowlist。
- Browser、BFF、Agent request body、模型或 Tool argument 都不能新增 permission。
- Safe Companion 初始階段使用空 allowlist；Event／Memory Tool 只在各自 Task 的 Consent 與人工 Gate
  完成後逐項開放。
- Core 每次 Tool 執行重新驗證，不使用 projection、cache 或 Agent context 作為授權來源。

### 4. Current turn 使用 private raw transport contract

Gate 1 synthetic implementation 使用 Core→Agent private request 直接傳送本輪最小必要文字，藉此重用現有
`input_text` orchestration，但必須同時符合：

- 僅在 server-side low-confidence Gate 通過後由 Core 傳送；Browser 不得直接呼叫 Agent Runtime。
- 傳輸前已驗證 `BASIC_VOICE` consent、assignment、session state 與 service identity。
- 除 in-process test 外一律使用 encrypted transport。
- Agent Runtime 只在 request lifetime 的記憶體處理，不寫 DB、一般 log、metric、trace、error、DLQ
  或 long-term memory。
- timeout、取消或撤回後停止後續模型／Tool，並釋放 request-scoped reference。
- response 不回填原始 current turn；error 只提供 bounded code／reason。
- Retention 需求改變、需要跨程序 retry，或 production privacy review 不接受 raw transport 時，
  必須改為 one-time reference contract 並另立 ADR。

完整 transcript／audio、完整 Prompt、Token 與 Secret 仍屬禁止進入一般記錄的 Restricted Data。

### 5. Voice Ticket 是短效、單次 capability

- BFF 向 Core 核發 endpoint 申請 Ticket；Core 從可信 ActorContext 推導 actor／tenant／elder。
- Ticket 綁定 version、issuer、audience、session、actor、tenant、elder、`BASIC_VOICE` purpose、
  consent ID/version、issued-at、expiry 與 nonce。
- Ticket 是 opaque bearer capability，只能透過 allowlisted header、WebSocket subprotocol或第一個受保護 frame
  傳送，不得放在 URL、log、metric、trace 或錯誤訊息。
- 預設 TTL 60 秒，設定上限 120 秒。
- Speech service 以 service identity 呼叫 Core consume endpoint；Core 驗簽、比對 conversation row 與 consent
  snapshot、重查 active consent，並以 row lock 執行 `CREATED → RECORDING`。
- 同一 session 只有第一次 consume 成功；過期、重播、cross-tenant、cross-elder、已取消或 consent
  版本失效一律拒絕且零 outbox／Candidate side effect。
- `BASIC_VOICE` revoke 必須取消同 consent 的 CREATED／RECORDING／PROCESSING／RESPONDING sessions，
  使未用 Ticket 與 active session 立即失效；不得影響其他 Consent Purpose。
- Gate 1 最小實作使用既有 `conversation_session` state 與 consent snapshot，不新增第二個正式狀態來源。
  若未來需要 reissue history、`consumed_at` 稽核或 key-rotation history，再以新 migration 擴充。

### 6. Synthetic provider profile

Gate 1 functional／failure-path 測試可使用 deterministic adapters：

- Speech：固定輸出 high／low confidence、timeout、cancel、TTS failure，涵蓋 `ZH_TW`、`NAN_TW`、
  `MIXED` 的流程行為。
- Model：固定 ALLOW、BLOCK、NO_DATA、timeout 與 schema failure。
- Projection：依 tenant／elder 分區，支援 duplicate、out-of-order、lag、rebuild、replay 與 tombstone 測試。

所有 evidence 必須保存 adapter name/version 並標示 `provider=synthetic`、
`production_approved=false`。Synthetic 結果不得宣稱：

- 真實國語／臺語辨識或合成品質；
- production latency、availability、data region 或成本；
- Bedrock Guardrails、Neptune 或 OpenSearch production readiness。

非 test profile 不得自動 fallback 至 synthetic adapter。

### 7. Event 與效能 Gate

- Gate 1 的 Event Candidate 全部需要照服員 verify／correct／reject；不採低風險 auto-verify。
- Memory Candidate 必須由長者明確 confirm 才能 ACTIVE。
- Voice／Agent／TTS 尚未統一的 latency／quality 門檻不阻塞 deterministic functional tests；
  evidence 只保存實測 baseline，不宣告達標。
- Production provider、語言品質、data region、成本與 performance pass threshold 仍是 Owner decision。

## Fallback、移除條件與期限

- Speech 或 Voice Ticket 不可用時，停止 canonical voice；可保留經 Core auth／consent 的 synthetic
  text-only staging path，但不得切回 legacy WebSocket 或宣稱 Voice Gate 完成。
- Agent／Tool dependency failure 使用 no-guess safe fallback，且不得產生 Candidate、正式寫入或 outbox。
- 到期前必須完成一次 review：核准 production provider／credential，或延長本 ADR 並記錄 Owner、理由
  與新期限。
- 下列任一條件成立時移除對應 synthetic runtime route：正式 provider conformance 通過、production
  credential verifier 上線，或 Gate 1 release evidence review 要求停止。
- Synthetic fixtures 可永久保留為 regression tests，但 production configuration 必須無法選用。

## 必要驗證

- 未驗證 caller、browser direct、錯誤 audience、過期與 replay credential 全部拒絕。
- Ticket missing/revoked consent、expiry、replay、cross-tenant／elder、核發後撤回與 active cancel。
- Low-confidence confirm 前零 Agent／Candidate／outbox。
- Core→Agent→Core 使用同一 `agent_run_id`，Tool scope 只能縮小不能擴張。
- Event／Memory 正式 transition 與 outbox 同交易，失敗零 side effect。
- Delete／revoke 後 projection replay、rebuild、restore 不可復活。
- Log、metric、trace、error response 不含 Token、完整 Prompt／Transcript／Audio 或 Ticket。
- Synthetic 主旅程連續五次，並保存實際 adapter／policy／schema／release version。

## 後果

- Domain、安全與 failure-path E2E 不必等待 production provider 選型即可開始。
- Voice Ticket、service identity 與 raw current-turn transport 都有明確 fail-closed contract。
- 現有 browser→legacy WebSocket 路徑不會因本 ADR 取得延長或 production 合法性。
- Production AWS application runtime、ASR／TTS、Bedrock／Guardrails、Graph provider、成本與效能門檻
  仍未完成，不得在文件、Demo 或 release evidence 中描述為已上線。
