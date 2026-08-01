# 成員 C（Isaac）｜Agent／RAG／Graph 範圍

依文件 12 §4.3 與 §5 WS-02。本檔是該分工在 repository 內的落地說明，
分工本身以文件 12 為準；兩者不一致時以文件 12 為準。

- Owner：Isaac
- Workstream：WS-02｜Agent／Retrieval／Graph
- Backup：D（杰倫）；同時擔任 WS-03 Speech／Elder App 的 Backup

## 負責元件

| 元件 | 狀態 |
| --- | --- |
| Conversation Orchestrator | 第一版（單輪＋顯式 purpose RAG gate） |
| Companion Agent | 骨架（Mock Provider） |
| Safety Evaluator | 骨架（deterministic 規則） |
| Context Builder | 第一版（3～5 個限長且帶引用的 RAG context） |
| Context Manifest | 骨架 |
| Agent Trace | 只有 ID 產生器 |
| Event Extractor Agent | 未開始 |
| Memory Candidate Agent | 未開始 |
| Knowledge Retrieval Planner | 第一版（受控 request → staging hybrid plan） |
| Model Router | 未開始 |
| Prompt Registry | 未開始 |
| OpenSearch Retrieval | 第一版 staging adapter／contract；AWS staging 實跑尚未完成 |
| Neptune Graph Projection | 未開始 |
| Agent／RAG／Graph Evaluation | 未開始（`evals/` 尚無內容） |

程式在 [`services/agent-runtime/`](../../services/agent-runtime/)，
契約在 [`contracts/schemas/agent/`](../../contracts/schemas/agent/) 與
[`contracts/schemas/tools/`](../../contracts/schemas/tools/)。

Staging 的治理例外僅限明確設定 `RAG_REQUIRE_OWNER_SIGNATURE=false` 的 unsigned development
override。它不會關閉外部 `RAG_ALLOWLIST_EXPECTED_SHA256` 比對，也不會略過來源、Chunk、
數量或完整 Allowlist 驗證；receipt／log 必須標示
`governance_status=UNSIGNED_DEVELOPMENT_OVERRIDE`、`production_approved=false`。Production
仍須正式簽署 Allowlist，並明確設定 `RAG_PRODUCTION_ENABLED=true`。目前 Human Review 與
AWS deployment／staging 實跑都尚未完成。

## 允許的操作

- 讀取已授權的 Session Context
- 讀取 `ACTIVE` Memory
- 讀取 Verified Event
- 建立 Event Candidate
- 建立 Memory Candidate
- 執行受限制的 RAG 與 Graph 查詢
- 消費 Outbox Event 並建立 Graph Projection

## 禁止的操作

- Agent 直接把 Memory 改為 `ACTIVE`
- Agent 直接把 Event 改為 `VERIFIED`
- Agent 修改 Consent
- Agent 直接發布家屬報表
- Agent 執行任意 SQL、Gremlin 或 OpenSearch DSL
- Agent 跨 `elder_id` 或 `tenant_id` 讀取資料
- 未確認記憶進入 Context
- 繞過 Core API 的高風險 Command Gate

文件 12 §4.6 的原文是「**C 不得自行決定正式 Domain State；透過 B 提供的 Core Command API**」。
上面的禁止清單都是這一條的展開。

## 跨成員依賴

| 對象 | 內容 |
| --- | --- |
| B（柏成） | 提供 ElderScope、Consent 與受控的 Core Tool API。Agent 的所有正式狀態變更都經由此。 |
| D（杰倫） | 提供確認後的 Transcript，接收 `reply_text`。D 不把 ASR Transcript 寫成正式事件（文件 12 §4.6）。 |
| E（Iris） | CI／CD、Staging 與部署整合。 |
| A（Harper） | 跨 Workstream 整合與 Contract 整合的 Accountable。 |

## Spike（文件 12 §21）

| 編號 | 內容 | Time-box | 狀態 |
| --- | --- | --- | --- |
| SP-02 | AgentCore Runtime＋Gateway：最小 Agent Run、Tool Call、Trace、部署方式 | 4h | 部分——有最小 Agent Run 與 trace id；**無 Tool Call、無部署方式** |
| SP-05 | Neptune Projection／Fallback：關係圖、刪除／停用、Aurora 降級 | 4h | 未開始 |
| SP-06 | OpenSearch Hybrid Retrieval：Keyword、Vector、Metadata Filter 三組查詢 | 4h | Adapt——程式與測試完成；尚待符合上述 staging 治理 gate、AWS Region／Host／權限做實測 |

Spike 結束必須決定 Adopt、Adapt、Mock with replacement date 或 Drop。

## 規格來源

規格優先序依根目錄 [`AGENTS.md`](../../AGENTS.md) §2。與本範圍最相關的是：

- 文件 09｜Multi-Agent、Agentic Workflow 與 Context Engineering — 主規格
- 文件 11｜測試策略、Agent Evaluation 與品質門檻 — Eval 部分
- 文件 10｜API、Event、Tool 與 Data Contracts §15（Agent Handoff）、§16（Tool Contract）
- 文件 06｜Domain Model、文件 07｜Security — 邊界條件

Google Drive 上的團隊文件與 `docs/` 內的版本快照若不一致，先與對應 Owner 確認再動；
不要自行挑一邊實作。

- [Multi-Agent Design](https://docs.google.com/document/d/1ZfkKMMW2tfu5nSXn74WncuN6VN2iVVOeJ5kDxMSVr4Q/edit)
- [API／Event／Tool／Data Contracts](https://docs.google.com/document/d/1s2iM5Yue8WdpVa04DmQm-F_jTkHrPVaSW5ZaFFXD1bA/edit)
- [Implementation／Team Ownership](https://docs.google.com/document/d/1OGa9igfGHILGPJE3PmvynP23LxA9FPsT8jPO_R-SG9o/edit)
- [Canonical Drive Folder](https://drive.google.com/drive/folders/1U9GNc6ptxAhLj94cVER_IYXBgdOO7aUa)
