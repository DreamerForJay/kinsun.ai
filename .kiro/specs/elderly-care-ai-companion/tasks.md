# 已封存：智慧長照 AI 陪伴系統舊實作計畫

> **狀態：LEGACY／不再執行。** 本 Spec 的 TypeScript、Lambda、Step Functions 與 DynamoDB 實作方向，已由 [ADR 0007](../../../docs/adr/0007-canonical-backend-and-aws-deployment-authority.md) 取代。此頁刻意不保留任何任務核取方塊，避免歷史完成標記被 Kiro 或讀者誤判為目前 canonical 主線進度。

原始任務清單已保留於 [`tasks.legacy.md`](tasks.legacy.md)，其中的完成標記、`115/115` 測試與 `29 Lambdas` 僅代表已退役架構的歷史紀錄，不是目前 Python Core／Agent Runtime／canonical AWS deployment 的驗收證據，也不得作為 Gate 1 完成度依據。

目前狀態與工作權威來源：

- Repository 規則與已實作範圍：[`AGENTS.md`](../../../AGENTS.md)
- Canonical backend 與 AWS deployment 決策：[ADR 0007](../../../docs/adr/0007-canonical-backend-and-aws-deployment-authority.md)
- Domain Core：[`services/core-api`](../../../services/core-api/)
- 受控 Agent Runtime：[`services/agent-runtime`](../../../services/agent-runtime/)
- 唯一 multi-role PWA／BFF：[`packages/frontend`](../../../packages/frontend/)
- 可實際呼叫的契約：[`contracts`](../../../contracts/)

若要繼續 Gate 1 工作，應建立或更新符合上述 canonical 架構的新 Spec，不得從 `tasks.legacy.md` 恢復執行。
