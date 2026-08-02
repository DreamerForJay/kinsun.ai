# Requirements Document: Gate 1 Agent Vertical Slice

## 1. 文件狀態與權威邊界

本 Spec 定義 `kinsun.ai` 第一條 canonical Gate 1 Vertical Slice 的**待實作增量**。它將既有產品、
Domain、Security 與 Test 規格轉成可執行工作，不取代下列權威來源：

1. `docs/01智慧長照 AI 陪伴系統－產品方向與範圍基準 v1.2.md`
2. `docs/01A智慧長照 AI 陪伴系統－使用者研究與 Demo Persona v0.2.md`
3. `docs/02智慧長照 AI 陪伴系統－使用者故事與驗收條件 v1.3.2.md`
4. `docs/05`、`docs/06`、`docs/07`、`docs/10`、`docs/11`
5. `AGENTS.md` 與 ADR 0007

尚未實作的 endpoint、event 或 schema 只留在本 Spec；實作完成前不得寫入 `contracts/`。
舊 `.kiro/specs/elderly-care-ai-companion/tasks.legacy.md`、`packages/backend` 與 legacy
Lambda／DynamoDB stack 不屬於本 Spec 的完成證據。

**狀態：Draft，需完成 Requirements Review 與 Owner Decisions 後才執行 tasks。**

## 2. 目標與成功條件

以林阿嬤（幸福日照中心、臺語／國臺混語、低數位操作能力）跑通一條可恢復、可追溯且不繞過
人工確認的主旅程：

1. Core 確認 `BASIC_VOICE` 同意後開始語音互動。
2. ASR 低信心時要求簡短確認，不假裝理解。
3. Agent 產生安全、簡短、符合語言偏好的回覆。
4. Event 與 Memory 只能先成為 Candidate。
5. Event 經照服員覆核；Memory 經長者明確確認。
6. 正式狀態與 outbox 在同一交易寫入 Aurora PostgreSQL。
7. Projection 可追蹤、可重建，且不成為授權來源。
8. 下一輪只重用同 elder、已確認、未撤回、未刪除且仍在 scope 內的資料。
9. Daily Summary 的每個重點可回查正式事件與證據。
10. 保存 Contract、Safety、Trace 與 Failure-path 證據。

張阿姨只用於證明同 tenant 不同 elder 的隔離；陳伯伯只用於有效派案與跨場域權限證據，不需
重跑完整語音主線。所有 Demo、測試與 Eval 資料必須是 Synthetic 或完成去識別化。

## 3. Current Baseline（不計入本 Spec 任務完成度）

目前已有：

- 唯一 Next.js multi-role PWA／BFF 與 server-side OAuth token 邊界。
- Python Core 的 Identity、RBAC＋ABAC、tenant／elder scope、Consent、Voice Session metadata、
  AgentRun／Core Tool gate、transactional outbox foundation 與部分 domain API。
- Agent Runtime 的單輪 Companion、Context Manifest、deterministic Safety、step ceiling、可設定
  Mock／Bedrock Model Provider、staging-only RAG，以及一次受控的
  `create_event_candidate` register → Tool → complete lifecycle。
- Frontend Voice UI state，但 low-confidence 目前只屬 UI state，不是可信 server-side gate。

目前尚缺 canonical audio/WebSocket／ASR／TTS、server-side low-confidence confirmation、Memory
Candidate 確認閉環、Event 人工覆核 E2E、Projection／Graph reuse、Daily Summary generation
worker、跨服務 E2E 與 CI quality gate。

## 4. Glossary

- **BFF**：`packages/frontend` 的 server-side boundary；browser access token 不得離開此邊界。
- **Core**：`services/core-api`；正式 Domain State、Authorization、Consent 與 Command Gate。
- **Agent_Runtime**：`services/agent-runtime`；受控模型、Safety、Context 與 allowlisted Tool 選擇。
- **Voice_Ticket**：Core 核發、短效、單次、綁 actor／tenant／elder／purpose 的語音連線憑證。
- **Event_Candidate**：模型或 deterministic extractor 提出的事件候選，尚不是 Verified Event。
- **Memory_Candidate**：等待長者明確確認的長期記憶候選，尚不可進入長期 Context。
- **Formal_State**：由 Core Command Gate 驗證後寫入 Aurora 的正式狀態。
- **Projection**：由正式事件重建的 Graph／Search working state，不是授權或正式狀態來源。
- **Restricted_Data**：完整逐字稿、音訊、完整 Prompt、Token、內部照護筆記及其他受限資料。

## 5. Requirements

### Requirement 1: Canonical Topology and Trusted Context

**User Story:** 身為系統 Owner，我希望所有正式互動只走 canonical 主線，避免 legacy backend
形成第二套授權與正式資料來源。

#### Acceptance Criteria

1. WHEN browser 發起任何正式 API 操作，THE SYSTEM SHALL 只經由 Next.js BFF 呼叫 Core，且
   browser SHALL NOT 直接呼叫 Core 或 Agent Runtime。
2. WHEN Core 呼叫 Agent Runtime，THE SYSTEM SHALL 從可信 server-side context 推導 actor、
   tenant、elder、assignment、consent purpose/version 與 policy version，不得信任 client 或模型
   提供的同名欄位作為授權依據。
3. WHEN 正式語音連線被建立，Core SHALL 核發短效、單次、綁 actor／tenant／elder／purpose 的
   Voice Ticket；Access Token 與 ID Token SHALL NOT 出現在 URL、browser-readable storage 或
   WebSocket query string。
4. THE SYSTEM SHALL NOT 對 `packages/backend`、legacy Lambda／DynamoDB／Step Functions stack
   新增功能或正式寫入，也 SHALL NOT 建立 DynamoDB＋Aurora dual write。
5. IF actor、tenant、elder、assignment、relationship、purpose 或 resource state 無法由可信 context
   證明，THEN Core SHALL deny by default，且不得產生 domain write、outbox 或 Tool side effect。

### Requirement 2: Purpose-Separated Consent and Immediate Revocation

**User Story:** 身為長者，我希望基本語音、逐字稿保存、事件擷取與長期記憶分別取得同意。

#### Acceptance Criteria

1. BEFORE 語音 Session 開始，Core SHALL 驗證有效的 `BASIC_VOICE` consent purpose 與版本。
2. WHEN 系統保存逐字稿、擷取照護事件或建立長期記憶候選，Core SHALL 分別驗證
   `TRANSCRIPT_STORAGE`、`CARE_EVENT_EXTRACTION`、`LONG_TERM_MEMORY`，不得以單一總開關替代。
3. WHEN 長者只同意 `BASIC_VOICE`，THE SYSTEM SHALL 仍允許基本陪伴，但 SHALL NOT 保存逐字稿、
   建立 Event Candidate 或 Memory Candidate。
4. WHEN consent 被撤回，THE SYSTEM SHALL 先停止對應用途的未來處理，並 SHALL 阻止 retry、
   replay、backfill、scheduler 或 projection rebuild 產生新的對應資料。
5. WHEN 長者說「停止」、「不要記」或「不要再提」，THE SYSTEM SHALL 優先停止相關流程，不得
   為提升互動率改寫意圖或自動重試。

### Requirement 3: Voice Session and Low-Confidence Confirmation

**User Story:** 身為林阿嬤，我希望系統聽不清楚時先確認，不要假裝理解或寫入錯誤資料。

#### Acceptance Criteria

1. THE SYSTEM SHALL 使用顯式 Voice State：`IDLE → RECORDING → ASR_PROCESSING →
   LOW_CONFIDENCE_CONFIRMATION（必要時）→ GENERATING → SAFETY_CHECK → TTS_PROCESSING →
   PLAYING → COMPLETED`，並支援 `CANCELLED`、`TIMED_OUT`、`FAILED`。
2. WHEN ASR confidence 低於版本化 Policy 門檻，THE SYSTEM SHALL 進入
   `LOW_CONFIDENCE_CONFIRMATION`，以簡短問題要求重說或確認關鍵內容。
3. UNTIL 低信心內容被明確確認，THE SYSTEM SHALL NOT 呼叫 Event／Memory Candidate Tool，也
   SHALL NOT 建立 transcript-derived formal state 或 outbox。
4. IF 使用者拒絕辨識內容、再次無法辨識、取消或逾時，THEN THE SYSTEM SHALL 結束或安全重試；
   同一輪自動重試最多一次，且不得留下 Candidate side effect。
5. WHEN TTS 失敗，THE SYSTEM SHALL 保留安全文字回覆與可恢復狀態，不得重跑 Domain command。
6. THE SYSTEM SHALL 保存 ASR／Speech／Policy 實際版本與 bounded metadata；完整音訊與逐字稿
   SHALL NOT 進入一般 log、metric 或 error response。

### Requirement 4: Safe, Short and Grounded Companion Turn

**User Story:** 身為林阿嬤，我希望 AI 使用熟悉的語言簡短回應，不提供危險醫療建議或虛構記憶。

#### Acceptance Criteria

1. WHEN Core 建立 Agent request，THE SYSTEM SHALL 依序組合 Policy、Auth、Consent、Current Turn、
   Session、Active Confirmed Memory、Verified Care Data、Graph／RAG 與 Output Constraints；不可用
   Projection 或模型輸出反推授權。
2. WHEN Agent 回覆長者，THE SYSTEM SHALL 遵守語言偏好與稱呼，預設不超過三個重點。
3. THE SYSTEM SHALL NOT 提供診斷、治療、停藥、改藥或取代專業照護決策的內容。
4. IF 缺少可信資料或 dependency 不可用，THEN THE SYSTEM SHALL 明確回覆資料不足或暫時無法回答，
   不得猜測家人行程、健康狀況或過往對話。
5. WHEN Safety decision 是 `BLOCKED`，THE SYSTEM SHALL 回傳安全替代訊息，且 SHALL NOT 執行
   Candidate Tool。
6. THE SYSTEM SHALL 維持受控執行上限：最多三次模型決策、兩輪 Tool、五次 Tool Call 與一次
   Rewrite／Context rebuild；本 Gate 1 流程不得引入無限迴圈、Agent Debate 或自由互相呼叫。

### Requirement 5: Event Candidate and Human Review Gate

**User Story:** 身為照服員，我希望 AI 只提出有來源的事件候選，由人工覆核後才成為正式事件。

#### Acceptance Criteria

1. WHEN `CARE_EVENT_EXTRACTION` 有效、Safety 允許且 extractor 找到事件，Agent Runtime MAY 提出
   schema-valid Event Candidate；模型 SHALL NOT 宣告事件已被人工確認。
2. WHEN Agent Runtime 執行 `create_event_candidate`，Core SHALL 重新驗證 service identity、tenant、
   elder、session、policy、consent、scope、state、idempotency 與 Tool allowlist。
3. THE SYSTEM SHALL 使用顯式 Event State：`CANDIDATE → NEEDS_REVIEW → VERIFIED／CORRECTED／
   REJECTED → SUPERSEDED`。
4. UNTIL 照服員依有效 assignment 完成人工覆核，Event Candidate SHALL NOT 進入摘要、Graph、
   Search、Family response 或後續對話事實。
5. WHEN 照服員 verify、correct 或 reject Event，Core SHALL 保存 reviewer、timestamp、前後值、
   reason 與 optimistic version。
6. IF authorization、consent、scope、state 或 version 驗證失敗，THEN Core SHALL 使用與不存在資源
   一致的回應，且 SHALL NOT 寫入 Event 或 outbox。

### Requirement 6: Memory Candidate and Explicit Confirmation Gate

**User Story:** 身為林阿嬤，我希望 AI 在記住穩定偏好或重要關係前先問我。

#### Acceptance Criteria

1. WHEN `LONG_TERM_MEMORY` 有效且內容屬穩定偏好、重要關係或固定作息，Agent MAY 提出
   Memory Candidate；一般閒聊、一次性事件、敏感健康推測與陪伴需求推估 SHALL NOT 成為候選。
2. THE SYSTEM SHALL 使用顯式 Memory State：`CANDIDATE → PENDING_CONFIRMATION → CONFIRMED／
   REJECTED／DEFERRED → ACTIVE → INACTIVE → DELETED`。
3. WHEN Memory Candidate 建立，THE SYSTEM SHALL 以簡短問題詢問長者是否保存，且 SHALL 保存
   source reference、schema/model/policy version 與 bounded confidence metadata。
4. UNTIL 長者明確確認，Memory Candidate SHALL NOT 成為 `ACTIVE`，也 SHALL NOT 進入 Context、
   Graph、摘要、Family response 或後續對話事實。
5. WHEN 長者拒絕、延後、說「不要記」或 consent 已撤回，Core SHALL 阻止 ACTIVE transition；
   拒絕不得產生正式 Memory write 或 activation outbox。
6. WHEN 授權照服員修正或處理候選，Core SHALL 仍依規格保留長者明確確認 Gate，不得由模型、
   Hook、retry、scheduler 或資料修復程序宣告確認完成。
7. WHEN Memory 被停用、刪除或撤回，THE SYSTEM SHALL 立即停止檢索，並以 tombstone 阻止 replay、
   projection rebuild 或 restore 使其復活。

### Requirement 7: Transactional Formal State and Outbox

**User Story:** 身為系統維運者，我希望正式狀態與事件發布具有一致性，不發生無保護 dual write。

#### Acceptance Criteria

1. WHEN Event 成為 `VERIFIED／CORRECTED` 或 Memory 成為 `ACTIVE`，Core SHALL 在同一個 database
   transaction 寫入 Formal State 與 transactional outbox entry。
2. IF transaction rollback、authorization failure、consent failure 或 optimistic conflict 發生，THEN
   THE SYSTEM SHALL NOT 留下 formal write 或 outbox entry。
3. WHEN 相同 idempotency key 被重送，Core SHALL 回傳同一安全結果或明確 conflict，不得建立重複
   Event、Memory 或 outbox。
4. THE SYSTEM SHALL 保存 correlation ID、causation ID、event version、schema version 與 resource
   version；不得只記錄 `latest`。
5. THE SYSTEM SHALL NOT 同步 dual-write Aurora 與 Graph／Search／Event Bus。

### Requirement 8: Projection and Confirmed Data Reuse

**User Story:** 身為林阿嬤，我希望下一次對話只引用我已確認、仍有效的資訊。

#### Acceptance Criteria

1. WHEN outbox event 被 consumer 處理，THE SYSTEM SHALL 使用顯式 Projection State：`PENDING →
   PROCESSING → SYNCED` 或 `FAILED → RETRYING → SYNCED／DEAD_LETTER`。
2. Projection consumer SHALL idempotent，並在每次處理前重新檢查 tenant、elder、formal state、
   consent、revocation、deletion 與 tombstone。
3. WHEN Core 組合下一輪 Context，THE SYSTEM SHALL 只讀取同 tenant／elder、`ACTIVE` Memory 與
   `VERIFIED／CORRECTED` Event，並記錄實際使用的 memory/event IDs。
4. IF Graph／Search 不可用、lagging 或資料不足，THEN THE SYSTEM SHALL 安全降級且不得從模型或
   projection 反推正式狀態。
5. WHEN duplicate、out-of-order、DLQ replay、rebuild 或 restore 發生，THE SYSTEM SHALL NOT 使
   `REJECTED／INACTIVE／DELETED` 或 consent-revoked 資料重新可見。
6. Cross-tenant 或 cross-elder projection query SHALL 回傳零筆可用 Context，且不得洩漏資源存在性。

### Requirement 9: Traceable Daily Summary

**User Story:** 身為照服員，我希望每日摘要精簡且每一點都能回到正式事件證據。

#### Acceptance Criteria

1. WHEN Daily Summary 產生，THE SYSTEM SHALL 只使用 `VERIFIED／CORRECTED` Event，不得使用
   Candidate、`NEEDS_REVIEW`、`REJECTED` 或未確認 Memory。
2. EACH summary item SHALL 至少包含可回查的 `source_event_id` 與 bounded evidence reference；
   Family response 不得包含 Restricted Data。
3. WHEN 某類資料不存在，THE SYSTEM SHALL 顯示「未提及」或「資料不足」，不得補出診斷或推論。
4. WHEN source Event 被修正、supersede、撤回或刪除，THE SYSTEM SHALL 將相關摘要標記為需重建，
   並在 rebuild 前重新檢查 scope 與 tombstone。
5. Daily Summary SHALL 先供授權照服員覆核；本 Gate 1 不得把 Draft Summary 當成已發布 Family
   Report 或發送 LINE／Email。

### Requirement 10: Privacy, Errors and Observability

**User Story:** 身為長者，我希望系統可追蹤失敗，但不把我的敏感內容寫進一般觀測資料。

#### Acceptance Criteria

1. General log、metric、trace tag 與 error response SHALL NOT 包含 Secret、Token、完整 Prompt、
   完整 Transcript、Audio、未覆核事件、內部照護筆記或 family-restricted data。
2. WHEN validation 或 permission 被拒絕，error response SHALL NOT 回填被拒絕的敏感原值。
3. Unauthorized 與 nonexistent 單一資源 SHALL 使用一致的狀態碼與 envelope，避免存在性探測。
4. THE SYSTEM SHALL 保存 bounded trace metadata，包括 API、Agent、Prompt、Model route、Policy、
   Guardrail、Tool schema、Context manifest、Speech、Graph 與 Release version。
5. Context Manifest 若跨服務傳遞，THE SYSTEM SHALL 使用 reference 或經核准的 Restricted Data
   contract；不得直接啟用目前內嵌逐字稿的 target Handoff shape。

### Requirement 11: Verification and Gate 1 Evidence

**User Story:** 身為 Quality Owner，我希望 Gate 1 的完成宣告具有可重跑的正常與失敗路徑證據。

#### Acceptance Criteria

1. THE SYSTEM SHALL 使用 Synthetic／De-identified fixture 驗證林阿嬤主線、張阿姨隔離與陳伯伯
   assignment scope，不得使用真實個資。
2. Test evidence SHALL 涵蓋正常、低信心、拒絕、撤回、失敗、逾時、重試與 idempotency。
3. Negative tests SHALL 涵蓋 cross-tenant、cross-elder、expired assignment、revoked share、
   unconfirmed Memory、unreviewed Event、Draft Report 與 Tool reauthorization failure。
4. Async tests SHALL 涵蓋 duplicate、out-of-order、DLQ replay、projection lag、rebuild 與 tombstone。
5. Contract changes SHALL 同步 JSON Schema、OpenAPI／AsyncAPI、valid/invalid examples 與對應 live
   verifier；尚未實作的介面不得提前寫入 executable contracts。
6. Gate 1 SHALL 保存可重跑的 Demo、Trace、Contract、Safety 與 Failure-path evidence；沒有實測的
   latency、quality 或 production capability SHALL NOT 被宣告達標。
7. THE SYSTEM SHALL 連續完成至少五次 Synthetic Gate 1 主旅程，且每次不得出現 cross-scope、
   confirmation bypass、Restricted Data log 或 replay resurrection。

### Requirement 12: Owner Decision Gates

**User Story:** 身為 Project Owner，我希望未決技術與品質門檻被明確阻擋，不由暫時程式偷偷定案。

#### Acceptance Criteria

1. BEFORE 實作 canonical ASR／TTS adapter，Owner SHALL 核准 provider、語言範圍、fallback、資料
   區域與測試門檻，並以 ADR 或核准紀錄保存。
2. BEFORE 啟用真實 Bedrock model／Guardrails，Owner SHALL 核准 model／inference profile、fallback、
   cost ceiling 與 safety evaluation gate。
3. BEFORE 建立 Graph production path，Owner SHALL 核准 Gate 1 graph slice、Neptune／替代 adapter、
   rebuild 與成本邊界。
4. Event Candidate 在 Gate 1 SHALL 採人工覆核；文件 05 允許的低風險自動 VERIFIED 與較嚴格規則
   之衝突 SHALL 保留為 Owner decision，不得在本 Spec 內默默啟用自動核准。
5. Voice／Agent／TTS latency 門檻因規格文件不一致，Owner SHALL 先核准統一門檻；在此之前只記錄
   實測 baseline，不宣告達標。
