# Implementation Plan: Gate 1 Agent Vertical Slice

## Overview

本計畫只列從目前 canonical baseline 到 Gate 1 閉環的**淨新增工作**。所有任務初始均未完成；
不得匯入或計算 `.kiro/specs/elderly-care-ai-companion/tasks.legacy.md`、`packages/backend`、legacy
Lambda／DynamoDB stack 或既有 foundation 的完成標記。

執行前先完成 Requirements Review、Design Review 與 Task Review。尚未實作的介面不得提前寫入
`contracts/`；每個 task 只有在 Acceptance Criteria 與必要測試有證據時才能標記完成。

## Tasks

- [ ] 1. 固定 Gate 1 traceability 與 Owner decision gates
  - [ ] 1.1 建立 Gate 1 AC → Domain State → Security Gate → Test Gate 對照
    - 以 `requirements.md` §5 與 `design.md` §13 為起點，逐項連回 docs 01A／02／05／06／07／10／11。
    - 明確標示 current baseline、net-new target、Owner decision 與 out-of-scope，避免把 target architecture 當成現況。
    - 記錄文件 05 低風險 Event auto-verify 與 Gate 1 全人工覆核的衝突；未決前維持較嚴格行為。
    - _Requirements: R11, R12_
  - [ ] 1.2 核准 canonical Voice／Speech 與效能門檻
    - 由 Owner 決定 ASR／TTS provider、國語／臺語／混語 Gate 1 範圍、data region、fallback、成本與 quality gate。
    - 統一 docs 01／02／07／11 不一致的 Voice／Agent／TTS latency 門檻；核准前只記 baseline，不宣稱達標。
    - 以 ADR 或核准紀錄保存 Owner、Expiry、Fallback 與移除條件。
    - _Requirements: R3, R12_
  - [ ] 1.3 核准 Gate 1 Graph 與 Model deployment 邊界
    - 決定 Graph first slice、Neptune／替代 staging adapter、rebuild 與成本邊界。
    - 決定 Bedrock model／inference profile、Guardrails、fallback 與 cost ceiling。
    - 不得把現有 adapter、AWS foundation 或 unsigned RAG 當成 deployment approval。
    - _Requirements: R4, R8, R12_
  - [ ] 1.4 收斂 Core↔Agent service identity、Tool scope 與 AgentRun authority
    - 選定且記錄唯一 AgentRun lifecycle：Core pre-register 後由 Runtime reuse，或 Runtime register
      且 Core companion path 不重複建立；不得讓兩套 authority 同時正式寫入。
    - 定義雙向 service authentication／credential contract；Agent Runtime 必須拒絕 browser direct
      access 與未驗證 caller，不得把 browser credential 轉送成 `SYSTEM_SERVICE`。
    - Tool allowlist／scope 只能由 Core 根據 trusted context、consent、policy、session server-side
      推導，不能由 browser 或模型擴張。
    - 規劃使用真實 Core guard 的 integration test，不以 MockTransport lifecycle test 代替。
    - _Requirements: R1, R5, R10, R12_
  - [ ] 1.5 核准 executable Agent Run 的 Restricted Data transport
    - 決定 current turn 使用 reference，或建立經核准的 private raw transcript service contract。
    - 合約必須涵蓋雙向 service auth、傳輸加密、最小化、bounded retention／timeout cleanup、
      audit 與 browser direct-access denial。
    - 邊界完成前，不把現行 `input_text` path 當成 canonical Gate 1 完成證據。
    - _Requirements: R1, R10, R12_

- [ ] 2. 建立 canonical Voice Ticket 與可信 Voice Session
  - **Dependencies:** Task 1.2
  - [ ] 2.1 檢查 baseline／ORM coverage 並設計 Voice Ticket 狀態
    - 先人工比對 frozen baseline、現有 Voice Session model 與 contract；不得直接使用 Alembic autogenerate 輸出。
    - 定義短效、單次、綁 actor／tenant／elder／purpose／expiry／nonce 的 ticket 與 consume semantics。
    - 如需 schema 變更，新增 Alembic revision，使用 Expand → Migrate → Contract，不修改已套用 migration。
    - _Requirements: R1, R2, R3_
  - [ ] 2.2 實作 Core Voice Ticket Command Gate
    - 從 trusted `ActorContext` 解析 scope，驗證 assignment 與 `BASIC_VOICE` consent/version。
    - unauthorized／nonexistent 使用一致回應；失敗不得建立 session、ticket 或 outbox。
    - ticket 成功使用後失效，過期、重播、cross-tenant、cross-elder 一律拒絕。
    - consent 在核發後撤回時，未使用 ticket 立即失效，active session 轉為取消並停止後續處理。
    - _Requirements: R1, R2, R10_
  - [ ] 2.3 實作 BFF Voice Ticket boundary
    - Browser 只呼叫 BFF；token 保留伺服器端，BFF 不把 cookie 或 raw token 送到 browser-readable voice URL。
    - 只轉發 allowlisted headers，將 server response 轉成既有 UI 可用狀態。
    - 同步 `zh-Hant`／`en` 字串與無障礙狀態，不改動 domain consent 或 elder language preference。
    - _Requirements: R1, R3, R10_
  - [ ] 2.4 新增 Voice Ticket 契約與驗證證據
    - endpoint 實作完成後才新增 JSON Schema／OpenAPI、valid/invalid examples 與 core live verifier。
    - 測試 missing/revoked consent、核發後撤回、active-session cancel、expired assignment、replay、
      cross-scope、錯誤不回填敏感值。
    - _Requirements: R1, R2, R10, R11_

- [ ] 3. 實作 canonical Speech 與 server-side low-confidence Gate
  - **Dependencies:** Tasks 1.2, 2
  - [ ] 3.1 建立 provider-neutral Speech adapter boundary
    - 外部 SDK 只出現在 adapter；實作 Owner 核准的 ASR／TTS route 與 synthetic fake。
    - 定義 Voice state、final transcript reference、confidence band、speech/model/policy version 與 bounded timeout。
    - 完整 audio／transcript 不進一般 log、metric 或 error response。
    - _Requirements: R3, R10, R12_
  - [ ] 3.2 實作 server-side low-confidence confirmation state machine
    - 低於 Policy threshold 時進 `LOW_CONFIDENCE_CONFIRMATION`，要求重說或確認關鍵內容。
    - reject、再次不清楚、cancel、timeout 時安全結束；同一輪自動 retry 最多一次。
    - consent 在 ASR 或低信心確認期間撤回時，立即取消 session，停止 ASR／TTS／retry／Agent。
    - 未確認或已撤回前禁止 Event／Memory extractor、formal write 與 outbox。
    - _Requirements: R2, R3, R11_
  - [ ] 3.3 完成 Voice UI 狀態與可恢復 fallback
    - 將既有 lowConfidence UI state 接到可信 server outcome，而非 client 自行判斷。
    - 呈現 recording／processing／confirmation／playing／cancel／timeout／offline／permission denied。
    - TTS failure 保留安全文字，不重跑 Agent 或 Domain command。
    - _Requirements: R3, R4, R10_
  - [ ] 3.4 驗證 Speech 正常與失敗路徑
    - 使用 Synthetic 國語、臺語、國臺混語測試集；保存實測 baseline，不虛構 latency／quality 數字。
    - 測試 low-confidence confirm/reject/repeat、ASR/TTS timeout、取消、offline 與零 Candidate side effect。
    - _Requirements: R3, R10, R11_

- [ ] 4. 串接 Consent-aware Safe Companion Turn
  - **Dependencies:** Tasks 1.4, 1.5, 2, 3
  - [ ] 4.1 由 Core 組合基礎可信 Agent Context
    - 本階段只組合 Policy→Auth→Consent→Current Turn→Session→Output Constraints，並保留
      Active Memory／Verified Event／Graph／RAG 的空 extension point 與 no-data fallback。
    - 排除 revoked／deleted／cross-scope data，保存實際 reference 與版本；confirmed-data reuse
      必須等 Task 5–7 完成後由 Task 7.3 接入。
    - 不把 client／model 送入的 actor、tenant、elder、consent 或 permission scope 當成授權。
    - _Requirements: R1, R2, R4, R10_
  - [ ] 4.2 以核准的 service transport 呼叫 private Agent Runtime
    - 僅在低信心 Gate 通過後，以 Task 1.4 的 service identity 與 Task 1.5 的 Restricted Data
      transport 呼叫 bounded Companion；本階段使用 Core server-derived 的空 Tool allowlist。
    - 語言偏好、稱呼與回覆長度來自 trusted profile；Safety block 時回安全替代內容且不執行 Tool。
    - dependency／資料不足時 no-guess fallback；不得切回 legacy WebSocket backend。
    - _Requirements: R1, R3, R4, R10_
  - [ ] 4.3 補齊 Companion service-auth／privacy／scope tests
    - 涵蓋未驗證 caller、browser direct access、醫療紅線、資料不足、model timeout、max-step、
      空 Tool allowlist，以及張阿姨資料不得進林阿嬤 Context。
    - 驗證 current-turn transport 的 auth／cleanup contract，且 error／log／trace 不含完整 transcript、
      prompt、token 或未覆核內容。
    - _Requirements: R1, R4, R10, R11_

- [ ] 5. 完成 Event Candidate 人工覆核閉環
  - **Dependencies:** Tasks 1.4, 4
  - [ ] 5.1 將受控 Event Candidate lifecycle 接入 canonical Core path
    - 重用現有 Runtime register→Tool→complete 的已測行為，但先依 Task 1.4 選定唯一 AgentRun
      authority；不得讓 Core companion path 與 Runtime 重複建立／完成 AgentRun。
    - Core 依 trusted context、`CARE_EVENT_EXTRACTION` consent、policy 與 session server-side 推導
      `create_event_candidate` allowlist；browser／模型不能要求或擴張 Tool scope。
    - 使用核准的 service identity 呼叫真實 Core guard；所有 repository query 明確帶 tenant scope，
      Candidate 不進 formal read path。
    - _Requirements: R1, R2, R5, R10_
  - [ ] 5.2 實作照服員 verify／correct／reject Command Gate
    - 驗證 role、assignment、tenant、elder、state、optimistic version 與 idempotency。
    - 保存 reviewer、timestamp、reason、修正前後值；Gate 1 不自動 VERIFIED。
    - formal transition 與 outbox 在同一 transaction；失敗零 side effect。
    - _Requirements: R5, R7_
  - [ ] 5.3 實作最薄照服員 Event review UI
    - 只顯示授權 scope 內 Candidate 與 bounded evidence，不洩漏完整 transcript／內部 prompt。
    - 支援 verify、correct、reject、conflict refresh 與清楚的來源／版本顯示。
    - _Requirements: R5, R10_
  - [ ] 5.4 新增 Event review contract、integration 與 negative tests
    - 實作後同步 schema、OpenAPI、event schema、examples、live verifier 與 traceability。
    - 以真實 Core service guard 驗證 canonical Core→Agent→Core lifecycle、唯一 AgentRun UUID、
      server-derived Tool scope 與未驗證 Runtime caller 拒絕，不只測 MockTransport。
    - 測試 cross-tenant／elder、expired assignment、consent revoked、version conflict、重送、失敗無 outbox。
    - 驗證 unreviewed/rejected Event 不進 Summary／Projection／Context。
    - _Requirements: R1, R5, R7, R10, R11_

- [ ] 6. 完成 Memory Candidate 與長者明確確認閉環
  - **Dependencies:** Tasks 1.4, 4
  - [ ] 6.1 檢查 Memory baseline 並定義 explicit-confirmation state machine
    - 人工比對 frozen baseline、現有 Memory model／API／enum；需要 schema 變更時新增 revision，不修改 baseline。
    - 固定 `CANDIDATE→PENDING_CONFIRMATION`，再分支為 `CONFIRMED→ACTIVE`、`REJECTED` 或
      `DEFERRED`；只有 `ACTIVE` 可後續轉為 `INACTIVE→DELETED`。
    - 定義 stable preference／important relationship／routine allowlist；排除一次性事件與敏感推測。
    - _Requirements: R2, R6, R7_
  - [ ] 6.2 實作 Agent Memory Candidate proposal 與 Core Tool Gate
    - 新 Tool 先定義 versioned schema／allowlist，再由 Core 重驗 service identity、scope、consent、state、idempotency。
    - Agent 只能提出 Candidate 與簡短確認問題，不能宣告人類已確認。
    - Safety block、低信心未確認、`LONG_TERM_MEMORY` 缺少／撤回時零 Candidate side effect。
    - _Requirements: R2, R4, R6_
  - [ ] 6.3 實作 Core confirm／reject／defer／deactivate／delete commands
    - Confirm 必須來自可信 elder confirmation context；照服員修正不能繞過長者確認 Gate。
    - ACTIVE transition＋outbox 同交易；reject/defer/stop/revoke 不得建立 ACTIVE Memory 或 activation
      outbox，但需保存防止重問、支援 idempotency 與稽核所需的最小化 non-active transition evidence。
    - delete/revoke 建立 tombstone 並立即停止 retrieval。
    - _Requirements: R6, R7, R8_
  - [ ] 6.4 完成 Elder confirmation UI／Voice interaction
    - 使用簡短、單一問題確認保存；支援 confirm、reject、later、stop 與逾時。
    - UI outcome 必須由 Core command 結果決定，不在 client 自行把 Candidate 標成 ACTIVE。
    - _Requirements: R3, R6, R10_
  - [ ] 6.5 新增 Memory contract、integration 與 negative tests
    - 實作後同步 schema、OpenAPI／event、examples、live verifier 與 traceability。
    - 測試 unconfirmed／rejected／deferred 不可檢索、cross-scope、revocation、delete、retry/replay/rebuild 不可復活。
    - _Requirements: R6, R7, R8, R11_

- [ ] 7. 實作可重建 Projection 與 confirmed-data reuse
  - **Dependencies:** Tasks 1.3, 5, 6
  - [ ] 7.1 定義 Event／Memory domain event 與 consumer contract
    - Producer/consumer 採 versioned immutable event；正式 state＋outbox 先完成，再由 relay 發布。
    - 每個 consumer 有專屬 idempotency、retry、DLQ、correlation／causation 與 projection state。
    - 實作完成後才加入 AsyncAPI／event schema 與 valid/invalid examples。
    - _Requirements: R7, R8, R11_
  - [ ] 7.2 實作 Gate 1 Graph／Search projection consumer
    - 使用 Owner 核准的 adapter；SDK 不進 domain／orchestration。
    - 每次 process/retry/replay/rebuild 前重查 formal state、consent、revocation、deletion、tombstone 與 scope。
    - duplicate／out-of-order idempotent；failure 不回滾 Core formal state。
    - _Requirements: R8, R10_
  - [ ] 7.3 實作 Core-authorized projection retrieval 與 Context reuse
    - Core 先授權，再查 projection reference，最後對 formal state 二次過濾。
    - 只回傳同 tenant／elder 的 ACTIVE Memory 與 VERIFIED/CORRECTED Event，記錄實際使用 IDs。
    - Graph unavailable／lagging 時安全降級，不從 projection 或模型推斷授權／正式狀態。
    - _Requirements: R4, R8, R10_
  - [ ] 7.4 驗證 projection failure 與 resurrection prevention
    - 測試 duplicate、out-of-order、DLQ replay、lag、rebuild、restore、delete/revoke tombstone。
    - Cross-tenant／elder query 必須零筆且不洩漏存在性。
    - _Requirements: R8, R11_

- [ ] 8. 產生可追溯 Daily Summary 供照服員覆核
  - **Dependencies:** Tasks 5, 7
  - [ ] 8.1 實作 verified-event-only Summary generation
    - 只讀 VERIFIED／CORRECTED Event；沒有資料顯示「未提及」／「資料不足」。
    - 每個 item 保存 source_event_id 與 bounded evidence reference，不新增診斷或原始資料外結論。
    - _Requirements: R9, R10_
  - [ ] 8.2 實作 Summary review／rebuild lifecycle
    - source correction／supersede／revoke／delete 時標記需重建，rebuild 前重驗 scope／tombstone。
    - Gate 1 只供照服員覆核，不建立 Published Family Report 或通知 side effect。
    - _Requirements: R8, R9_
  - [ ] 8.3 實作最薄照服員 Summary evidence UI
    - 顯示摘要重點、來源事件、bounded evidence、資料不足與最後更新／版本。
    - 未授權、跨 scope、未覆核事件及 Restricted Data 不得顯示。
    - _Requirements: R9, R10_
  - [ ] 8.4 新增 Summary integration／negative／contract tests
    - 測試 rejected／unreviewed Event 不進摘要、每個 item 有來源、修正後 rebuild、cross-scope。
    - endpoint/event 實作後同步 contracts、examples 與 live verifier。
    - _Requirements: R9, R11_

- [ ] 9. 建立 Gate 1 E2E、Safety／Privacy Evidence 與 Quality Gate
  - **Dependencies:** Tasks 2–8
  - [ ] 9.1 建立 Synthetic Gate 1 fixtures 與 evaluation datasets
    - 林阿嬤跑完整主線；張阿姨驗同 tenant cross-elder；陳伯伯驗 assignment／cross-site。
    - 涵蓋國語、臺語、混語、低信心、拒絕、撤回、醫療紅線、資料不足與失敗路徑。
    - 不放真實個資、完整 production prompt 或未去識別 transcript。
    - _Requirements: R3, R4, R10, R11_
  - [ ] 9.2 建立跨服務 Gate 1 E2E
    - 驗證 consent→voice→low-confidence confirm→safe reply→Event/Memory Candidate→review/confirm→outbox→projection→reuse→summary。
    - 另跑拒絕、撤回、Agent/Graph failure、DLQ replay；任何失敗不得產生未授權 side effect。
    - _Requirements: R1–R11_
  - [ ] 9.3 建立 Restricted Data 與 authorization evidence checks
    - 掃描 log、metric、trace、error response；不得有 Secret、Token、完整 Prompt／Transcript／Audio。
    - 驗證 unauthorized／nonexistent equivalence、cross-tenant／elder、expired assignment、revoked share。
    - _Requirements: R10, R11_
  - [ ] 9.4 保存五次連續 Demo 與 failure-path evidence
    - 連續至少五次 Synthetic 主旅程，保存實際 contract、trace、safety、model/policy/schema/release versions。
    - 只報告實測 latency／quality；未達或未核准門檻清楚標示，不虛構 production readiness。
    - _Requirements: R11, R12_
  - [ ] 9.5 建立 CI quality gate
    - 執行 Frontend、Core、Agent、contract、integration 與 Gate 1 E2E 的適當測試層級。
    - 保留 migration-from-empty、negative security、replay/tombstone 與 Restricted Data gate。
    - 不使用 `--no-verify` 或跳過安全檢查；失敗不得宣告 Gate 1 完成。
    - _Requirements: R7, R8, R10, R11_

## Completion Rule

只有 Tasks 1–9 的 required acceptance evidence 全部存在，且 Requirements／Design／Tasks 已 review，
才能宣告本 Spec 完成。AWS foundation、adapter 程式、Mock 測試、legacy task 勾選或單次 happy-path
Demo 都不足以代表 Gate 1 完成。
