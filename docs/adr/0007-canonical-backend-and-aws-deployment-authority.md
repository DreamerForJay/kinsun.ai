# ADR 0007：後端主線、AWS IaC 權威與 Legacy 退役

- 狀態：Accepted for staging implementation；production 仍需 Project Owner／Quality Owner 核准
- 日期：2026-08-02
- 決策依據：本次 repository 工作指示與既有架構不變量
- 相關：[ADR 0003](0003-core-api-framework-and-schema-authority.md)、
  [ADR 0004](0004-agent-runtime-into-monorepo.md)、
  [ADR 0006](0006-frontend-stack-and-app-topology.md)
- 解除：`AGENTS.md` §11「兩套後端去留」與「IaC 工具」待決項

## 背景

Repository 目前同時存在兩種互不相容的後端方向：

1. `packages/frontend` BFF → `services/core-api`（FastAPI／Aurora）→
   `services/agent-runtime`。
2. `packages/backend`＋現有 `infrastructure/`（Lambda／DynamoDB／另一套 Cognito／CDK）。

正式架構已規定 Aurora PostgreSQL／Domain Core 是唯一 System of Record。若兩套後端
同時演進，會產生兩套授權、Domain State、Cognito client 與無保護 dual write。

一般 HTTP 流程已走第一條路徑；但設定 `NEXT_PUBLIC_WS_URL` 時，語音頁面仍可選擇性直連
舊 WebSocket。該路徑會把 Cognito token 放在瀏覽器可讀狀態及 URL，不能成為 production
身分模型。

2026-08-02 對 `us-west-2` staging AWS Console 的後續盤點顯示：既有 Cognito User Pool、
兩個 OpenSearch Serverless collection、ECR repositories、`CDKToolkit`，以及已部署的
legacy `ElderlyCareStack-dev`。Canonical foundation 建立前沒有 canonical ECS cluster 或
RDS／Aurora database，且只有 default VPC。舊 stack 的存在不是 canonical application
deployment 證據，也不得用來更新主線；新 foundation 不重建 Cognito／OpenSearch。

## 決策

### 1. Canonical application topology

```text
Browser
  └─ HTTPS／OAuth → packages/frontend（唯一 Web App 與 BFF）
                       → services/core-api（唯一 Domain／Authorization 寫入入口）
                          ├─ Aurora PostgreSQL（唯一正式交易資料來源）
                          └─ services/agent-runtime（private AI runtime）
                               └─ Bedrock／OpenSearch projection
```

- `services/rag-ingestion` 只做離線 staging ingestion，不是線上 Domain API。
- `speech-gateway` 與各 worker 依此邊界補齊，不得繞過 Core 寫正式狀態。
- OpenSearch、Neptune、cache 與 Agent memory 都是可重建 projection／working state。
- Browser 不得直接呼叫 Core 或 Agent Runtime；access token 留在 BFF 的 HttpOnly cookie。
- 正式語音連線必須改用 Core 核發、短效、單次、綁定 actor／tenant／elder／purpose 的
  ticket；Access Token 與 ID Token 不得出現在 URL。

### 2. `packages/backend` 立即進入 Legacy Freeze

- 不再加入功能、endpoint、資料模型或 AWS adapter。
- 只允許安全修補、inventory、遷移協助及移除依賴。
- 不得部署為 production artifact，也不得把其測試描述為 canonical backend 證據。
- `knowledge-etl`、`search`、`reranker` 的 deprecated 決策維持：ingestion 屬於
  `services/rag-ingestion`，retrieval／ranking 屬於 `services/agent-runtime`。
- `packages/shared` 不是 Domain authority；跨服務 contract 以 `contracts/` 為準。

### 3. AWS CDK v2 是 canonical IaC 工具，但現有 stack 是 Legacy

選擇 CDK v2 是為了延續 repository 既有 TypeScript toolchain 與 AWS 架構文件；這項選擇
不代表現有 `infrastructure/lib/elderly-care-stack.ts` 符合新架構。該 stack 會建立
DynamoDB、另一套 Cognito、Lambda REST／WebSocket 與 Step Functions，因此：

- 禁止部署現有 `ElderlyCareStack`；只允許 synth／唯讀檢查。
- Canonical CDK stack 必須重新建模 Next.js BFF、Python Core、Agent Runtime、Aurora 與
  private service boundaries。
- 既有 Cognito 與 OpenSearch 先以 externally managed reference 使用；完成 drift、ownership
  與 replacement 分析前，不匯入、不重建、不刪除。
- 所有新的持久 staging 資源必須由 canonical CDK 建立或立即匯入；Console 只用於盤點、
  緊急操作或經記錄的短期 spike，不能成為唯一配置來源。
- staging region 固定為 `us-west-2`；production account／region 仍須另行核准。

### 4. Legacy 語音路徑是限時 staging／demo 例外

- 預設關閉，只能使用 synthetic data，不得進 production。
- Owner：成員 C（Integration）；Expiry：2026-08-16。
- Fallback：現有 BFF → Core → Agent Runtime 的文字流程。
- 到期或 canonical voice E2E 通過（取較早者）後，以 single-use voice ticket 取代。
- Legacy DynamoDB 結果不得視為正式 Domain State。

### 5. 遷移與移除門檻

- 禁止 DynamoDB＋Aurora dual write，也不得對非 synthetic data 做 shadow write。
- 每項 consumer 切換前先有 canonical contract、authorization／consent negative test、
  failure path 與 rollback。
- AWS 若存在 legacy data，必須另做具 provenance、idempotency、consent、tombstone 與
  reconciliation 的 migration plan，不直接 bulk copy。
- 前端不再引用 legacy WebSocket/token flow、canonical 服務完成 E2E、AWS inventory 與
  rollback evidence 完成後，才可用獨立變更刪除 `packages/backend` 與舊 stack。

## Staging AWS 建立規則

2026-08-02 已依明確授權建立 `kinsun-staging-foundation-v1`，包含 VPC、NAT、ECS cluster、
四個空 ECR repository、Aurora PostgreSQL Serverless v2、Secrets、Logs、IAM 與 SSM external
references。它重用既有 Cognito 與 `kinsun-rag-staging`，未建立第二套。Aurora 已套用 deletion
protection 與 Snapshot deletion／replacement policy，foundation stack 亦已啟用 termination
protection；canonical Agent ECS task role 已以只追加方式加入既有 OpenSearch read-only data
policy，原 ingestion／runtime principals 未移除。Frontend、Core API、one-shot migration 與
Agent Runtime 的正式 container image 已可在本機重現 build／smoke；獨立的 asset-free
application stack 也已完成，但尚未推送 release digest、尚未部署 ECS task definition／service，
也不表示 Web、Core 或 Agent Runtime 已上線。

同日以只含一筆原地 SSM Parameter 修改的 CloudFormation change set，將 external Cognito
app-client reference 修正為 `kinsun-web-bff-staging`；canonical parameter 以單值
`AllowedValues` fail closed，避免後續更新重新選用 legacy client。Cognito 本身未重建或匯入。

首版 staging 必須：

- 重用既有 Cognito 與 `kinsun-rag-staging` OpenSearch collection，不建立第二套。
- 只讓 Next.js BFF 成為 public entry；Core、Agent Runtime、Aurora 不公開。
- 使用 synthetic data、最小 capacity、短 log retention、ECR lifecycle 與成本告警。
- 標記 `Project=kinsun.ai`、`Environment=staging`、`DataClass=synthetic-only`、
  `ManagedBy=aws-cdk`、`Owner` 與 `ExpiresAt`。
- 不建立 production、Neptune、第二套 RAG、Legacy Lambda／DynamoDB backend。

## 後果與未決事項

- 新功能只進 canonical services，避免繼續擴張第二套後端。
- 四個 container image 與 application-stack constructs 已完成本機驗證；initial stack 固定
  `desiredCount=0`，staging 每個 service 上限 1 task、每個 task 0.5 vCPU／1 GiB。部署前仍須
  完成 ECR immutable digest preflight、foundation runtime DB Secret／migration repository update、
  migration、synthetic consent bootstrap、Cognito callback 與 smoke gates。
- Next.js 14 已不在目前 upstream security release 的修補線；在新 ADR 選定並驗證受支援
  major version前，禁止公開部署 Frontend 或把 service scale 到 1。
- staging 月費上限、24/7 或 demo-hours、production
  account／region、正式 Bedrock model／Guardrail、retention 與 voice performance gate 仍需
  Owner 決策。Aurora foundation 已固定 min 0／max 1 ACU、15 分鐘 auto-pause。
- 本 ADR 只宣稱 staging foundation 已部署，不宣稱 application runtime、production approval
  或 migration 已完成。
