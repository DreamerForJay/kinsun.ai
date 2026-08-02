# Legacy backend — frozen

本目錄的 Lambda／DynamoDB backend 已由 ADR 0007 定為 legacy，不是正式後端主線。

- 不加入新功能、endpoint、資料模型或 AWS adapter。
- 只允許安全修補、inventory、遷移協助及移除依賴。
- 不得部署到 production，也不得與 Aurora dual write。
- HTTP／OAuth 主線是 `packages/frontend` BFF → `services/core-api` →
  `services/agent-runtime`。
- RAG ingestion 屬於 `services/rag-ingestion`；retrieval／ranking 屬於
  `services/agent-runtime`。

選填的舊 WebSocket voice path 僅是 synthetic staging/demo 的限時例外，預設關閉，
不得把 Cognito token 放入 production URL。完整退役門檻見
[`docs/adr/0007-canonical-backend-and-aws-deployment-authority.md`](../../docs/adr/0007-canonical-backend-and-aws-deployment-authority.md)。
