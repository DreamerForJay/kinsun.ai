# RAG Current Chunk Bundle

包含 17 個來源、726 個 current Chunk。

## 目錄規則

- `approved/`：目前 Allowlist v002 核准的 6 個來源、262 Chunk，可供第一輪 staging ingestion。
- `pending-revalidation/`：來源 2、3、4；已補 Delivery ZIP，但尚未更新 Allowlist。
- `not-authorized/`：已有 current Chunk，但目前不在 Embedding Allowlist。

## 重要限制

Ingestion 程式只能讀取 `data/rag-chunks/approved/`。
不得掃描整個 `data/rag-chunks/`，否則會把未授權資料送進 Embedding。

## 2026-08-02 變更：not-authorized 全數升級

上面的目錄規則描述的是 bundle 交付當下的狀態。`SHA256SUMS.txt` 與
`data/rag-manifest/all_current_chunk_catalog_20260802.json` 同樣是交付當下的紀錄，
其中的路徑與 `category` 欄位刻意保留原樣，作為 bundle 原始形態的證據。

目前實際狀態：

- `approved/`：14 個來源、578 Chunk（原 6 來源 262 Chunk，加上原 not-authorized 的
  8 個來源 316 Chunk）。
- `pending-revalidation/`：來源 2、3、4，未變動，仍被程式硬性拒絕。
- `not-authorized/`：已清空，但程式層守衛保留，避免日後有人再放東西進去。

來源 7「老年期營養手冊」一度卡住：它的 41 個 Chunk 沒有 `official_source_url`，而
`build_index_document` 當時只找 `official_source_url` 與 `source_url`。實際上資料一直
帶著 `official_source_page_url`（國健署的官方頁面），只是程式沒有讀它。修法是讓
`build_index_document` 把 `official_source_page_url` 列為最後備援——直接檔案連結仍然
優先，但有官方頁面就足以引用，不需要為此捏造網址。

**升級的是可 ingestion 範圍，不是審查狀態。** Allowlist 的
`human_source_review` 仍為 `NOT_COMPLETED`、`project_owner_risk_acceptance` 仍為
`NOT_SIGNED`、`production_status` 仍為 `BLOCKED`，新增的 8 個 `sources[]` 條目都帶有
說明「無人工來源審查紀錄」的 `scope_note`，每個新 Chunk 條目維持
`review_status=needs_review` 與 `production_gate=BLOCKED`。

新增內容包含衛教與照護指引（失智症、營養、防跌、健康照護附錄），風險由 Chunk 層級標記
承擔。全部 578 個 Chunk 中，33 筆 `risk_level=high_red_line` 與 34 筆
`stop_normal_rag=true` 會被 `agent_runtime/rag/filters.py` 的檢索過濾排除，實際可進入
Agent context 的是 485 筆。這些數字由 `tests/integration/test_approved_dataset.py`
守著，資料集再變動時測試會紅。

**這是目前唯一在執行的範圍限制。** 既有 6 個來源的 `sources[]` 帶有人工審查寫下的
`scope_note`（例如 UCLA 量表註明「僅描述性內容，停用施測、診斷與自動計分」），新升級的
8 個沒有等價的來源層級約束。
