# RAG Current Chunk Bundle

包含 17 個來源、726 個 current Chunk。

## 目錄規則

- `approved/`：目前 Allowlist v002 核准的 6 個來源、262 Chunk，可供第一輪 staging ingestion。
- `pending-revalidation/`：來源 2、3、4；已補 Delivery ZIP，但尚未更新 Allowlist。
- `not-authorized/`：已有 current Chunk，但目前不在 Embedding Allowlist。

## 重要限制

Ingestion 程式只能讀取 `data/rag-chunks/approved/`。
不得掃描整個 `data/rag-chunks/`，否則會把未授權資料送進 Embedding。
