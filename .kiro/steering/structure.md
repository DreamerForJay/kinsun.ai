---
inclusion: always
---

# Repository Structure

```text
kinsun.ai/
├── .kiro/                 Kiro specs、steering 與 hooks
├── apps/                  刻意保持空；前端在 packages/frontend（ADR 0006）
├── contracts/             OpenAPI、JSON Schema、valid/invalid examples
├── data/                  資料相關資產邊界
├── design-system/         MASTER.md：視覺、RWD、無障礙規範
├── docs/                  產品、domain、security、architecture、ADR
├── evals/                 Agent evaluation 與報告
├── infra/                 IaC 邊界；工具尚待決策
├── ops/                   維運資產
├── packages/
│   ├── frontend/          單一 multi-role PWA＋BFF（Next.js App Router）
│   ├── shared/            前端／backend 共用 TypeScript 型別
│   └── backend/           第二套後端，尚未收斂；見 AGENTS.md §1
├── scripts/               Contract 與 repository 驗證腳本
├── services/
│   ├── core-api/          正式 Domain Core 與 API
│   ├── agent-runtime/     受控 Agent Runtime
│   └── rag-ingestion/     RAG ingestion 與 allowlist 建置
└── tests/                 跨服務測試邊界
```

完整結構與工作方式：
#[[file:AGENTS.md]]
#[[file:README.md]]

## 分層規則

- API route 只處理 HTTP 邊界、呼叫 service 並包裝 envelope。
- Service 協調 domain、policy、repository 與 outbox，不組裝 HTTP 錯誤。
- Policy 採 deny-by-default，正式授權資料必須由 server-side context 取得。
- Repository 查詢必須明確攜帶 tenant scope。
- ORM model 只負責資料映射；schema 變更由新的 Alembic revision 管理。
- 外部 Provider/SDK 只能出現在 adapter 或 provider 邊界，不散入 domain 與 orchestration。
- Contract 只描述已實作、可實際呼叫的介面；未實作設計放在 `docs/` 或 Kiro Spec。

## 變更同步

- Endpoint 或 envelope 改變時同步 contract、examples、live verification 與 divergence 文件。
- Domain state 改變時同步 migration、tests、traceability 與必要文件。
- 不建立第二份 schema、authorization mapping 或 response mapping 作為競爭權威來源。
