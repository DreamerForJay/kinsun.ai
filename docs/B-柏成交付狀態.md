# B（柏成）Domain Backend／Security 交付狀態

- 更新日期：2026-08-01
- 角色：B — Domain Backend／Security Owner
- 範圍：Python Core API、Aurora schema、Domain State、RBAC + ABAC、Consent、Idempotency、Transactional Outbox，以及 Event producer／consumer foundation。

## 已完成

### Domain 與 API

- Elder：授權範圍查詢、單筆讀取、長者本人 actor 綁定與不可探測的 404。
- Consent：依 Purpose 分離的建立、查詢、撤回；撤回立即阻止未來處理，並建立 deletion workflow。
- Voice Session metadata：建立、查詢、受控狀態轉移、取消與完成；每次操作重新檢查 Consent。Audio／WebSocket transport 明確標示 `NOT_CONFIGURED`。
- Care Event：只能先建立 Candidate；覆核後才能成為 Verified，並支援 Correct／Reject／Exclude。
- Memory：Candidate、Confirm／Reject／Defer、Update、Delete；只有確認且未撤回的 Active Memory 能進正式讀取。
- Daily Summary：只接受 Verified Event 作為來源；支援 Draft、Review、Rebuild 與 stale 標記。
- Family Report：Draft、Publish、Withdraw；家屬端只可讀取符合 relationship scope 且仍為 `PUBLISHED` 的版本。
- Assignment：建立、查詢、確認、開始與完成；檢查 tenant、care unit、worker membership、時間範圍與用途 scope。
- Tool：Allowlist、schema、第二次 Core 授權、Consent／Policy version、Idempotency 與 restricted-data audit protection。
- Deletion：撤回同意時建立 deletion request／store job；具顯式 request/item state machine、tenant-scoped hash Tombstone 與 transactional outbox。Aurora `MEMORY` 已可在可信 policy／legal-hold gate 後清除內容；未配置的外部 store 會維持 `PARTIAL_FAILED`，不會偽造完成。

### 資料與事件安全

- 新 Alembic revisions 只做增量變更；凍結的 v0.1 baseline SQL 與 checksum 未修改。
- Outbox 支援 `SUPPRESSED` 與 terminal `DEAD_LETTER`；relay 在發布前重查 Consent、tenant scope、aggregate state 與通用 hash Tombstone，並將 typed publisher failure 依 `retryable` 與 attempt limit 決定 `FAILED` 重試或 `DEAD_LETTER`。
- Domain Event 使用嚴格 envelope；payload 遞迴拒絕 Transcript、Audio、Prompt、Secret、Token。
- Consumer 以 `consumer name + event_id` 做交易內 idempotency；Replay 不重做副作用，失效 Consent 或 tombstone 事件會被抑制。Handler／processing failure 只暴露穩定 `reason_code`，以 `RETRY`／`DEAD_LETTER` disposition 交由未來 queue adapter 處理，不保存原始 exception message。
- 正式 EventBridge／每個 Consumer 專屬 SQS／DLQ／Redrive 尚未綁定，避免在 AWS Region、Account、IaC 未定案前偷偷鎖定技術決策。

### Contract 與可重現 Demo

- OpenAPI 覆蓋目前 runtime 的 44 個 operations。
- JSON Schema 使用 `additionalProperties: false`；包含正常與必須被拒絕的範例。
- 已建立 AsyncAPI 與 Domain Event Envelope；validator 會檢查 JSON Schema、OpenAPI、AsyncAPI 及 examples。
- Live verifier 會比對 runtime operation parity，並驗證 protected GET 在未配置 authenticator 時 fail closed。
- `scripts/reset_demo.ps1 -ConfirmLocalReset` 可從空 DB 套用全部 migration 並載入固定 Synthetic Demo Seed。
- Seed 包含三位合成人物、Active／Revoked Consent、Confirmed Assignment、Verified Event、READY／NEEDS_REVIEW Summary、Confirmed Memory、Draft／Published／Withdrawn Report、成功／失敗通知、失敗 projection 與待發布 outbox。

## 本次整理已驗證

```text
Source base:             fef3009 (origin/main)
Working branch:          feature/member-b-core-hardening
Unit tests:              406 passed
Integration tests:       95 passed
Total Core tests:        501 passed
Ruff check:              All checks passed
Ruff format:             162 files already formatted
Static contracts:        all checks passed (44 Core operations, 1 AsyncAPI channel)
Live contract verifier:  all 44 runtime operations contracted; protected GET fail-closed passed
Docker Compose config:   passed
Git diff check:          passed
```

本次使用 Python 3.12.10、PostgreSQL 16，並將 `TEST_DATABASE_URL` 明確限制到本機
`localhost:15432/kinsun_test`。Integration suite 已實際執行 Alembic upgrade／downgrade／
rebuild 測試；live verifier 也已在 process 內啟動 Core lifespan 並驗證 `/ready` 與所有
protected GET 的 fail-closed response。

本次沒有執行 `scripts/reset_demo.ps1`，因此沒有覆寫本機 `kinsun` demo 資料，也不把
Synthetic Seed reset 列為本次結果。需要重建 Demo 時，必須另外明確執行帶
`-ConfirmLocalReset` 的破壞性指令。

## Core Gate Evidence｜2026-08-01T14:08:24+08:00

- `release_candidate`：`feature/member-b-core-hardening`
- `source_revision`：工作樹基於 `fef3009aa5289bcf6f4070661633bbe130bfc176`；最終 revision 以 PR head 為準。
- `infrastructure_version`：PostgreSQL 16 Alpine，Docker Compose 本機環境，host port `15432`。
- `contract_version`：Core API v1、Agent Runtime v1、Domain Event Envelope v1。
- `policy_version`：目前 branch 的 Core authorization／consent policy；model、prompt 與 dataset 不屬本次 Core Gate。
- `test_run_id`：`core-local-20260801-1408-tw`
- `environment`：Windows、PowerShell、Python 3.12.10、pytest 8.4.2；因 `uv` 不在 PATH，本次以明確 `-SkipSync` 執行既有 `.venv`，屬 degraded local verification，不冒充 locked release gate。
- `passed／failed／skipped`：Core pytest `501／0／0`；Ruff、static contract、live contract、Compose config 與 diff check 全部通過。
- `zero_tolerance_results`：Core negative authorization、tenant-local role mismatch、cross-tenant／cross-elder、consent、restricted payload 與 fail-closed 測試為 0 failure。
- `defects`：本次 Core Gate 無未解失敗。
- `known_risks`：repository 尚無可執行的 Staging E2E／rehearsal harness；停用中的 deploy-staging workflow 仍只有 TODO，故未宣稱 E2E 五連跑完成。AWS resource binding 與正式政策核准亦仍待 Owner 決策。
- `approvers`：B 本機自驗完成；Backup A Pair Review 與 Quality Owner E Gate approval 待 PR。
- `links`：`scripts/verify_core.ps1`、`services/core-api/tests/`、`contracts/`、本文件。
- `trace／log／screenshot／video`：Core CLI 可由單一 script 重現；Staging 級 artifacts 待 A／E 提供環境與 E2E harness 後產出。

### Definition of Done 狀態

- [x] Unit／Contract／必要 Integration Test 通過。
- [x] Authorization、Consent、Cross-Elder Negative Test 通過。
- [x] Schema、Error、Idempotency、Version 規則由 contract 與測試驗證。
- [x] 文件與本機重跑指令已更新。
- [ ] Code 合併 main；目前待 commit／PR／merge。
- [ ] Backup A Pair Review 與 Quality Owner E approval。
- [ ] Staging Vertical Slice E2E 連續成功五次與完整 Demo artifacts。

## 2026-08-01 B hardening 補強

- `GET /api/v1/me` 不再用 `actor_role` 偽裝 `display_name`；現在從正式 `actor` table
  讀取姓名，並先確認 active tenant membership、active actor 與正式角色一致。
- Tenant 與 care-unit membership 現在都必須符合 authentication context 的 tenant-local
  `role_code`；全域 `actor_type` 不再能替代另一個租戶角色，並有 PostgreSQL role-mismatch
  negative test 防止角色混淆回歸。
- 新增 `ActorRepository`、unit tests，以及會驗證 `DC Worker` 正式姓名的 PostgreSQL
  integration assertion。
- 新增 `scripts/verify_core.ps1`，一次執行 locked sync、test DB safety probe、unit、
  integration、Ruff、static contract、live contract、Compose config 與 `git diff HEAD --check`；
  migration roundtrip 需要明確確認，無 `uv` 時預設 fail closed，只有顯式 `-SkipSync` 才允許
  degraded local verification，且任何 native command 非零 exit code 都會立即失敗。
- 修正 README 的 API 數量、Agent Runtime OpenAPI 與 ORM coverage 過時資訊。
- 修正停用中的 PR workflow：改用 `uv.lock`、PostgreSQL service、獨立 test DB、Core
  unit／integration、Agent Runtime、contract parity 與 dependency audit。workflow 仍依
  團隊最新 commit 保持停用，重新啟用需 A／E 決策與 GitHub runner 驗證。

## 需要 Owner／其他工作流決策，不可由 B 假裝完成

- Cognito User Pool／JWT verifier、AWS Region、Account／Environment 與 IaC 工具。
- EventBridge、SQS、DLQ、Redrive 的實際 AWS resource 與 deployment binding。
- Retention、Legal Hold、Backup Restore、外部 store 刪除驗證與 Offboarding 正式政策；現有 Core state machine 只接受可信 policy decision 且 fail closed，不能代替正式政策核准。
- D：WebSocket audio、ASR low-confidence confirm、TTS 與 voice performance。
- C：Agent Runtime／Handoff、RAG、Graph／OpenSearch projection 實作。
- E：LINE／Email delivery adapter、雲端部署、Observability 與 CI quality gate。

上述未決項目已保留 fail-closed 或 provider-neutral 邊界；目前不得描述成已部署或已可在 AWS 正式運行。

## 本機重跑

完整 Core Gate 不會重設 demo 資料：

```powershell
docker compose up -d postgres
.\scripts\verify_core.ps1 -ConfirmTestDatabaseMigrations
```

若需要刻意重建 Synthetic Demo Seed，才另外執行以下破壞性指令：

```powershell
.\scripts\reset_demo.ps1 -ConfirmLocalReset
```

有安裝 `uv` 時，驗證 script 會先執行 frozen sync；若 `uv` 不在 `PATH`，預設會
fail closed。只有本機已存在可信 `.venv` 且接受非 locked 結果時，才可明確加入
`-SkipSync`。若本機 5432 已被其他 PostgreSQL 使用，可指定替代測試埠：

```powershell
.\scripts\verify_core.ps1 -PostgresPort 15432 -SkipSync -ConfirmTestDatabaseMigrations
```
