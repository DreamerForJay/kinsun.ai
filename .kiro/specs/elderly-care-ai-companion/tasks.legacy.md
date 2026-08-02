# 已封存的實作計畫：智慧長照 AI 陪伴系統

> **LEGACY／不可作為目前進度依據。** 這是已由 [ADR 0007](../../../docs/adr/0007-canonical-backend-and-aws-deployment-authority.md) 取代的 TypeScript、Lambda、Step Functions 與 DynamoDB 歷史任務清單。下方完成標記、`115/115` 測試與 `29 Lambdas` 不代表目前 Python Core、Agent Runtime、canonical AWS deployment 或 Gate 1 已完成。請以 [`tasks.md`](tasks.md) 與 repository 根目錄 [`AGENTS.md`](../../../AGENTS.md) 判斷現況；不得繼續執行本檔任務。

## 概述

本計畫將智慧長照 AI 陪伴系統的設計分解為可逐步執行的編碼任務。採用 TypeScript 作為主要實作語言，以 Next.js PWA 為前端、AWS Serverless 為後端架構。任務按照依賴順序安排，確保每一步都能在前一步的基礎上構建。

## 任務

- [x] 1. 建立專案結構與核心型別定義
  - [x] 1.1 初始化 Next.js 專案與 monorepo 結構
    - 建立 Next.js PWA 專案（含 PWA manifest、service worker 配置）
    - 設定 monorepo 結構：`packages/frontend`、`packages/backend`、`packages/shared`
    - 設定 TypeScript、ESLint、Prettier 共用配置
    - 設定測試框架（Vitest + fast-check）
    - _需求：A01.4_

  - [x] 1.2 定義核心共用型別與介面
    - 建立 `packages/shared/types/` 目錄
    - 定義 Language、RecordingState、EventType、ReviewStatus、MemoryCategory 等列舉
    - 定義 ElderProfile、PersonaRecord、ConversationRecord、EventRecord、MemoryRecord、SummaryRecord 等資料模型介面
    - 定義 API 請求/回應型別
    - _需求：B01.2, B01.4, D01.3_

  - [x] 1.3 定義 DynamoDB Single-Table 鍵值設計與存取模式
    - 建立 `packages/backend/src/db/` 目錄
    - 實作 PK/SK 組合函式（ELDER#、CG#、FM#、AUDIT# 等前綴）
    - 定義 GSI1、GSI2 的鍵值產生邏輯
    - 建立 DynamoDB DocumentClient 封裝層
    - _需求：H01.2, B04.1_

  - [x] 1.4 設定 AWS CDK/SAM 基礎架構模板
    - 建立 `infrastructure/` 目錄
    - 定義 DynamoDB Table（含 GSI）、S3 Buckets、Cognito User Pool
    - 定義 API Gateway REST + WebSocket 端點骨架
    - 定義 KMS Key、CloudWatch Log Group
    - _需求：H01.1, H02.1, H02.2, H02.3_

- [x] 2. 實作認證與權限控制
  - [x] 2.1 實作 Cognito 認證整合
    - 建立 `packages/backend/src/auth/` 模組
    - 實作 JWT Token 驗證 Lambda Authorizer
    - 定義角色（Elder、Caregiver、Family、Admin）與 Cognito Group 對應
    - 實作 AuthorizationContext 介面與解析邏輯
    - _需求：H01.1_

  - [x] 2.2 實作資料隔離中間層
    - 實作 `validateDataAccess()` 函式，驗證請求者對 elder_id 的存取權限
    - 實作 DynamoDB 查詢層強制注入 elder_id 條件
    - 建立角色權限矩陣配置檔
    - _需求：H01.2, H01.3, D03.2_

  - [x]* 2.3 撰寫 Property Test：Elder 級資料隔離（Property 11）
    - **Property 11：Elder 級資料隔離**
    - 隨機生成多 Elder 資料與跨 Elder 查詢，驗證任何資料存取請求返回的資料 elder_id 必須與授權 elder_id 一致
    - **驗證需求：D03.2, H01.3**

  - [x]* 2.4 撰寫單元測試：權限控制
    - 測試各角色存取權限邊界
    - 測試跨 Elder 存取被拒絕
    - 測試未授權角色操作被拒絕
    - _需求：H01.1, H01.2, H01.3_

- [x] 3. 檢查點 - 確保所有測試通過
  - 確保所有測試通過，如有問題請詢問使用者。

- [x] 4. 實作語音互動工作流協調層
  - [x] 4.1 實作 Step Functions Express Workflow 定義
    - 建立 `packages/backend/src/workflow/` 模組
    - 定義語音互動工作流的 ASL（Amazon States Language）JSON
    - 實作各節點的 WorkflowNodeConfig（含 timeoutSeconds、retryPolicy、fallbackAction）
    - 實作 Router Lambda 接收 WebSocket 訊息並啟動工作流
    - _需求：J01.1, J01.2_

  - [x] 4.2 實作降級回應機制
    - 建立 DEGRADATION_STRATEGIES 配置
    - 實作降級回應選擇邏輯（根據錯誤類型選擇預錄語音/靜態文字/純文字）
    - 實作節點失敗後的 fallback 處理
    - 上傳預錄降級語音至 S3（音檔資產待 Demo 素材準備階段補上；S3 路徑與選取邏輯已就緒）
    - _需求：A05.1, A05.2, J01.3_

  - [x] 4.3 實作 Trace ID 傳播與監控日誌
    - 實作 traceId 在各 Lambda 之間的傳播機制
    - 建立 ErrorLog 格式化工具（確保不含 PII）
    - 實作 CloudWatch Metrics 寫入（延遲、成功率、錯誤率）
    - 配置 X-Ray tracing（API Gateway tracingEnabled；Lambda X-Ray 待各元件 Lambda 建立時開啟 Active tracing）
    - _需求：J04.1, J04.2, J04.3, A05.3_

  - [x]* 4.4 撰寫 Property Test：有限重試上界（Property 3）
    - **Property 3：有限重試上界**
    - 隨機生成錯誤序列，驗證單一節點重試次數永不超過 maxAttempts
    - **驗證需求：A02.5, A05.2**

  - [x]* 4.5 撰寫 Property Test：Trace ID 傳播一致性（Property 16）
    - **Property 16：Trace ID 傳播一致性**
    - 隨機生成多階段處理流程，驗證所有階段日誌包含相同 trace ID
    - **驗證需求：J04.2**

  - [x]* 4.6 撰寫 Property Test：監控日誌 PII 去除（Property 17）
    - **Property 17：監控日誌 PII 去除**
    - 隨機生成包含 PII 模式的日誌內容，驗證寫入 CloudWatch 的記錄不含 PII
    - **驗證需求：J04.3**

- [x] 5. 實作 ASR 語音辨識引擎
  - [x] 5.1 實作 ASR 語言路由邏輯
    - 建立 `packages/backend/src/asr/` 模組
    - 實作 ASREngine 介面與語言路由函式
    - 國語/英語路由至 AWS Transcribe Streaming
    - 臺語/客語路由至 SageMaker Endpoint
    - 混語偵測邏輯與分段處理（先以 Transcribe 轉寫並取得逐段語言，臺客語段落再送 SageMaker 重新辨識）
    - _需求：A02.1, A02.3_

  - [x] 5.2 實作 ASR 信心分數處理與重試
    - 實作信心分數閾值判斷邏輯
    - 信心分數低於閾值時觸發「請再說一次」回應
    - 實作 ASR 服務逾時重試策略（指數退避，沿用 workflow RetryTracker 與 asr 節點政策）
    - 記錄 ASR 服務端點、模型版本與辨識耗時至日誌
    - _需求：A02.2, A02.4, A02.5_

  - [x]* 5.3 撰寫 Property Test：ASR 語言路由正確性（Property 1）
    - **Property 1：ASR 語言路由正確性**
    - 隨機生成語言代碼組合，驗證路由決策正確性
    - **驗證需求：A02.1**

  - [x]* 5.4 撰寫 Property Test：信心分數閾值分類（Property 2）
    - **Property 2：信心分數閾值分類**
    - 隨機生成 0.0-1.0 浮點數，驗證閾值判斷與降級行為觸發
    - **驗證需求：A02.2, B01.5**

- [x] 6. 實作 Context Composer 與 LLM 對話生成
  - [x] 6.1 實作 Context Composer
    - 建立 `packages/backend/src/context/` 模組
    - 實作 Token 預算分配策略（systemPrompt、persona、memories、summary、searchResults、history）
    - 實作動態注入邏輯：時間、天氣、近期摘要、Confirmed Memory
    - 實作 usedItems 追溯記錄
    - 嚴格確保僅 confirmed 狀態的記憶被納入事實區段
    - _需求：A04.1, J02.1, J02.2, J02.3_

  - [x] 6.2 實作 LLM Engine 對話生成
    - 建立 `packages/backend/src/llm/` 模組
    - 整合 Amazon Bedrock (Claude) API 呼叫（Converse API）
    - 實作 Persona 設定注入（語言偏好、稱呼、回覆長度）
    - 實作「不知道就說不知道」的行為指引
    - _需求：A03.1, A04.2, A04.3_

  - [x]* 6.3 撰寫 Property Test：Token 預算約束（Property 4）
    - **Property 4：Context Composer Token 預算約束**
    - 隨機生成不同大小的 context items，驗證產出 Prompt Token 數不超過預算
    - **驗證需求：A04.1, J02.2, J02.3**

  - [x]* 6.4 撰寫 Property Test：僅已確認記憶作為事實（Property 5）
    - **Property 5：僅已確認記憶作為事實**
    - 隨機生成混合狀態的記憶集合，驗證 Prompt 事實區段僅含 confirmed 記憶
    - **驗證需求：A04.2**

- [x] 7. 實作 Guardrail Engine 與醫療安全護欄
  - [x] 7.1 實作 Guardrail Engine
    - 建立 `packages/backend/src/guardrail/` 模組
    - 整合 Bedrock Guardrails ApplyGuardrail API
    - 實作醫療安全攔截規則（diagnosis、medication_change、treatment_decision、dosage_recommendation）
    - 實作緊急情境偵測與固定安全指引回應（胸痛→119、跌倒→不要動、意識不清→119），優先於一般護欄檢查執行
    - _需求：H04.1, H04.2, J03.2_

  - [x] 7.2 建立護欄測試案例集
    - 建立 `packages/backend/src/guardrail/test-cases.json`
    - 包含各類醫療安全攔截測試案例
    - 包含緊急情境偵測測試案例
    - 包含正常對話放行測試案例
    - _需求：H04.3, J03.3_

  - [x]* 7.3 撰寫單元測試：護欄攔截與緊急偵測
    - 測試醫療建議類內容被攔截
    - 測試緊急關鍵字觸發安全指引
    - 測試正常對話不被攔截
    - _需求：H04.1, H04.2, H04.3_

- [x] 8. 實作 TTS 語音合成引擎
  - [x] 8.1 實作 TTS Engine
    - 建立 `packages/backend/src/tts/` 模組
    - 整合 Amazon Polly（國語 TTS）
    - 整合 SageMaker Endpoint（臺語/客語 TTS）
    - 實作語言偏好路由（根據 Persona 設定）
    - 實作 TTS 失敗降級（回退至文字顯示）
    - _需求：A03.2, A03.3, A03.4_

- [x] 9. 檢查點 - 確保語音互動核心管線測試通過
  - 確保所有測試通過，如有問題請詢問使用者。（53/53 測試通過：db/auth/workflow/asr/context/llm/guardrail/tts）

- [x] 10. 實作 Event Extractor 事件擷取器
  - [x] 10.1 實作 Event Extractor 核心邏輯
    - 建立 `packages/backend/src/event-extractor/` 模組
    - 整合 Bedrock LLM 進行對話事件擷取（飲食、活動、睡眠、用藥陳述、情緒、重要事件）
    - 實作 JSON Schema 驗證擷取結果（zod）
    - 實作信心分數判斷：低於閾值標記為 needs_review
    - 確保用藥相關僅記錄原始陳述，不推論遵從度（於擷取 prompt 明確規範）
    - _需求：B01.1, B01.2, B01.3, B01.4, B01.5_

  - [x] 10.2 實作事件持久化與必要欄位驗證
    - 實作事件寫入 DynamoDB 邏輯
    - 驗證必要欄位完整性（eventDate、eventType、originalUtterance、confidence、sourceConversationId）
    - 實作 GSI1/GSI2 鍵值自動產生
    - 設定 DynamoDB TTL（依資料保留政策）
    - _需求：B01.2, B01.4, H03.1_

  - [x]* 10.3 撰寫 Property Test：結構化輸出 Schema 驗證閘門（Property 6）
    - **Property 6：結構化輸出 Schema 驗證閘門**
    - 隨機生成合法/非法 JSON 結構，驗證不符合 Schema 的輸出永不被持久化
    - **驗證需求：B01.2, J03.1**

  - [x]* 10.4 撰寫 Property Test：實體必要欄位完整性（Property 7）
    - **Property 7：實體必要欄位完整性**
    - 隨機生成缺少不同欄位的實體，驗證持久化前必須包含所有必要欄位
    - **驗證需求：B01.4, D01.3**

- [x] 11. 實作 Memory Manager 記憶管理器
  - [x] 11.1 實作候選記憶產生邏輯
    - 建立 `packages/backend/src/memory/` 模組
    - 實作 generateCandidates() — 從對話中識別穩定偏好、重要關係、固定作息
    - 確保閒聊內容與敏感推測不被轉為候選記憶（於產生 prompt 明確規範，並以 schema 驗證必要欄位）
    - 為每筆候選記憶記錄 sourceConversationId、createdAt、confidence
    - _需求：D01.1, D01.2, D01.3_

  - [x] 11.2 實作記憶確認、拒絕與檢索流程
    - 實作 confirm() — 將候選記憶標記為 confirmed，記錄確認者與時間
    - 實作 reject() — 將候選記憶標記為 rejected
    - 實作 retrieve() — 僅檢索 confirmed 且 isActive 的記憶，嚴格以 elder_id 隔離
    - 實作語音確認問題觸發邏輯（於工作流層級：Memory_Manager 產生候選記憶後由對話流程觸發確認語句，詳見 workflow 模組）
    - _需求：D02.1, D02.2, D02.3, D02.4, D03.1, D03.2_

  - [x] 11.3 實作記憶更正與刪除
    - 實作 update() — 更新記憶內容並記錄 auditTrail
    - 實作 delete() — 跨儲存刪除（DynamoDB + OpenSearch 向量索引，透過可注入的 VectorIndexClient）
    - 確保刪除後的記憶不再被檢索引用
    - 保存變更稽核紀錄
    - _需求：D04.1, D04.2, D04.3_

  - [x]* 11.4 撰寫 Property Test：拒絕的記憶永不持久化為已確認（Property 10）
    - **Property 10：拒絕的記憶永不持久化為已確認**
    - 隨機生成確認/拒絕操作，驗證拒絕的記憶永不被已確認記憶檢索返回
    - **驗證需求：D02.2**

  - [x]* 11.5 撰寫 Property Test：刪除操作跨儲存完整性（Property 12）
    - **Property 12：刪除操作跨儲存完整性**
    - 隨機生成跨多儲存位置的資料項目，驗證刪除後所有儲存位置都查不到
    - **驗證需求：D04.2, H03.3**

  - [x]* 11.6 撰寫 Property Test：修改稽核完整性（Property 9）
    - **Property 9：修改稽核完整性**
    - 隨機生成修改操作序列，驗證 auditTrail 記錄完整不可覆蓋
    - **驗證需求：B03.2**

- [x] 12. 實作 Summary Generator 每日摘要產生器
  - [x] 12.1 實作 Summary Generator 核心邏輯
    - 建立 `packages/backend/src/summary/` 模組
    - 實作 EventBridge 觸發的 Lambda Handler
    - 實作摘要產生邏輯（涵蓋飲食、活動、睡眠、用藥陳述、重要事件）
    - 優先使用 Caregiver 已確認之事件資料
    - 為摘要中每項內容標註原始事件 ID（sourceEventIds）
    - 確保不新增原始事件中不存在的診斷或醫療判斷
    - _需求：B02.1, B02.2, B02.3, B02.4, B03.3_

  - [x]* 12.2 撰寫 Property Test：摘要內容可追溯性（Property 8）
    - **Property 8：摘要內容可追溯性**
    - 隨機生成事件集合與對應摘要，驗證每項摘要內容都有對應的有效事件 ID
    - **驗證需求：B02.3**

- [x] 13. 檢查點 - 確保事件擷取與記憶管理測試通過
  - 確保所有測試通過，如有問題請詢問使用者。

- [x] 14. 實作搜尋引擎與 RAG 衛教知識檢索
  - [x] 14.1 實作 OpenSearch Serverless 索引建立
    - 建立 `packages/backend/src/search/` 模組
    - 實作 health-knowledge 索引 mapping（含 BM25 text + KNN vector 欄位）
    - 實作 memory-vectors 索引 mapping
    - 建立索引管理工具（建立、更新、刪除索引）
    - _需求：E03.1_

  - [x] 14.2 實作 Hybrid Search（BM25 + Vector KNN）
    - 實作口語問題轉換為可檢索查詢（保留原始問題）
    - 實作 BM25 關鍵字搜尋
    - 實作 Vector KNN 語意搜尋（使用 Bedrock Embedding）
    - 實作結果合併與去重邏輯（保留各結果來源分數）
    - 實作 Metadata Filtering（source_agency、service_type、region、effective_date、risk_level、review_status）
    - _需求：E01.1, E01.2, E02.1, E02.2, E02.3, E03.1, E03.2_

  - [x] 14.3 實作 Reranker 重新排序
    - 建立 `packages/backend/src/reranker/` 模組
    - 實作多因素重新排序（queryRelevance、sourceCredibility、personaApplicability、recency、reviewStatus）
    - 實作 Top-N 截斷邏輯（僅將前 N 筆送入 LLM）
    - 記錄排序依據與結果順序
    - _需求：E04.1, E04.2, E04.3_

  - [x] 14.4 實作有根據的衛教回答
    - 整合搜尋結果至 LLM 回答產生流程
    - 實作來源標註（文件名稱、發布機關）
    - 實作「僅供參考，不作為醫療診斷依據」附加說明
    - 無相關結果時明確回覆「不知道」
    - _需求：E01.3, E01.4, E05.1, E05.2, E05.3_

  - [x]* 14.5 撰寫 Property Test：搜尋結果有效性過濾（Property 13）
    - **Property 13：搜尋結果有效性過濾**
    - 隨機生成混合狀態/日期的文件集合，驗證結果不含 needs_review 或過期文件
    - **驗證需求：E02.2, E02.3**

  - [x]* 14.6 撰寫 Property Test：搜尋結果去重（Property 14）
    - **Property 14：搜尋結果去重**
    - 隨機生成有重疊的 BM25/KNN 結果，驗證合併後不存在重複 chunk_id
    - **驗證需求：E03.2**

  - [x]* 14.7 撰寫 Property Test：Reranker Top-N 截斷（Property 15）
    - **Property 15：Reranker Top-N 截斷**
    - 隨機生成不同長度的排序結果，驗證送入 LLM 的恰好為前 N 筆
    - **驗證需求：E04.2**

- [x] 15. 實作知識庫 ETL 管線
  - [x] 15.1 實作知識庫文件處理管線
    - 建立 `packages/backend/src/knowledge-etl/` 模組
    - 實作 manifest 建立（來源機關、標題、版本、適用地區、授權資訊）
    - 拒絕無來源資訊的文件
    - 實作文件解析、清理、Chunk JSONL 產生
    - 實作 Metadata 標註（預設 review_status 為 needs_review）
    - 實作 Embedding 產生與 OpenSearch 索引寫入
    - _需求：G01.1, G01.2, G02.1, G02.2_

- [x] 16. 實作通知服務
  - [x] 16.1 實作 Notification Service
    - 建立 `packages/backend/src/notification/` 模組
    - 整合 Amazon SNS + SES
    - 實作摘要通知發送（每日/每週頻率）
    - 實作高風險事件即時通知
    - 實作靜默時段判斷
    - 實作連續失敗通知（3 次連續互動失敗觸發）
    - 實作取消訂閱功能
    - _需求：A01.5, C03.1, C03.2, C03.3, C03.4_

  - [x]* 16.2 撰寫單元測試：通知服務
    - 測試靜默時段內不發送通知
    - 測試高風險事件即時通知
    - 測試連續失敗計數與通知觸發
    - _需求：A01.5, C03.1, C03.3_

- [x] 17. 檢查點 - 確保搜尋引擎與通知服務測試通過
  - 確保所有測試通過，如有問題請詢問使用者。

- [x] 18. 實作前端 PWA — 語音互動介面
  - [x] 18.1 實作語音錄製與播放元件
    - 建立 `packages/frontend/src/components/voice/` 目錄
    - 實作 VoiceInteractionClient（MediaRecorder API 錄音、Web Audio API 播放）
    - 實作錄音狀態視覺動畫（idle、recording、processing、playing）
    - 實作麥克風權限偵測與白話引導
    - 實作首頁大型錄音按鈕 UI
    - _需求：A01.1, A01.2, A01.3_

  - [x] 18.2 實作 WebSocket 即時通訊
    - 建立 `packages/frontend/src/services/websocket.ts`
    - 實作 WebSocket 連線建立（JWT Token 驗證）
    - 實作音訊串流傳送
    - 實作轉譯結果接收與語音回覆接收
    - 實作斷線自動重連與本地暫存
    - _需求：A01.1, A01.2_

  - [x] 18.3 實作同意管理介面
    - 建立同意說明頁面（白話文字說明錄音內容、保存期限、刪除方式）
    - 實作同意授予/撤回流程
    - 未授予同意時禁用麥克風
    - _需求：A06.1, A06.2, A06.3, A06.4_

- [x] 19. 實作前端 PWA — 照護者後台
  - [x] 19.1 實作多長者概覽頁面
    - 建立 `packages/frontend/src/app/dashboard/` 目錄（專案採 Next.js App Router，與 pages/ 慣例等價）
    - 顯示每位 Elder 的最後互動時間、今日互動次數、摘要狀態、待覆核事件數
    - 僅顯示該 Caregiver 有權限的 Elder 資料（由後端 API 依 authorizedElderIds 過濾）
    - 不使用未經定義的風險標籤，僅呈現客觀數據
    - _需求：C01.1, C01.2, C01.3_

  - [x] 19.2 實作長者詳情頁面
    - 建立 AI 擷取事件、記憶管理、每日摘要等分頁區塊（design.md REST API 未定義 GET 長者基本資料端點，故基本資料/衛教內容區塊暫以摘要分頁替代，待後續補上對應端點）
    - 敏感欄位遮罩規劃於 API 層（task 20 REST handler）依角色權限執行，而非前端遮蔽
    - 為每項資料顯示更新時間與資料來源（事件顯示信心分數、記憶顯示確認者與確認時間）
    - _需求：C02.1, C02.2, C02.3_

  - [x] 19.3 實作事件修正與覆核介面
    - 實作事件內容、review_status 的編輯功能
    - 顯示修正次數與來源對話 ID（完整逐項 diff 檢視留待對話逐字稿檢視頁面實作時擴充）
    - 實作事件篩選（日期範圍、事件類型、審查狀態）
    - 實作事件連結回溯至原始對話 ID（design.md REST API 未定義逐字稿查詢端點，故先以 ID 顯示）
    - _需求：B03.1, B03.2, B03.4, B04.1, B04.2, B04.3, B04.4_

  - [x] 19.4 實作記憶管理介面
    - 實作候選記憶列表（確認/修正/拒絕操作）
    - 實作已確認記憶列表（檢視/更正/停用/刪除操作）
    - 實作記憶變更稽核紀錄顯示
    - _需求：D02.3, D04.1_

- [x] 20. 實作 REST API 端點
  - [x] 20.1 實作對話與事件 API
    - 實作 POST /v1/conversations/start（建立對話 session）
    - 實作 GET /v1/elders/{elderId}/events（取得事件列表，支援篩選）
    - 實作 PUT /v1/events/{eventId}（修正事件）
    - 加入 Lambda Authorizer 權限驗證
    - _需求：B04.1, B04.4, B03.1_

  - [x] 20.2 實作記憶 API
    - 實作 GET /v1/elders/{elderId}/memories（取得記憶列表）
    - 實作 PUT /v1/memories/{memoryId}/confirm（確認記憶）
    - 實作 DELETE /v1/memories/{memoryId}（刪除記憶）
    - 加入 elder_id 隔離驗證
    - _需求：D02.3, D04.1_

  - [x] 20.3 實作摘要、搜尋與報表 API
    - 實作 GET /v1/elders/{elderId}/summaries（取得摘要列表）
    - 實作 POST /v1/search/health（衛教知識搜尋）
    - 實作 GET /v1/elders/{elderId}/reports（週/年報表）
    - 實作 GET /v1/caregivers/{caregiverId}/dashboard（照護者概覽）
    - _需求：B02.3, E01.1, A07.1, C01.1_

  - [x] 20.4 實作 Persona 與同意 API
    - 實作 PUT /v1/elders/{elderId}/persona（更新 Persona）
    - 實作 POST /v1/consent/grant（授予同意）
    - 實作 POST /v1/consent/revoke（撤回同意）
    - _需求：A06.1, A06.3_

- [x] 21. 檢查點 - 確保前端與 API 整合測試通過
  - 確保所有測試通過，如有問題請詢問使用者。（102/102 單元/屬性測試通過；CDK synth 成功打包全部 14 個 REST Lambda + Authorizer；前端 Next.js build 成功）

- [x] 22. 實作資料保留與刪除策略
  - [x] 22.1 實作資料保留政策
    - 配置 S3 Lifecycle Policy（語音檔 90 天、知識庫無限）
    - 配置 DynamoDB TTL（對話 1 年、事件 2 年、候選記憶 30 天、摘要 2 年、稽核 3 年）
    - 實作 TTL 觸發時的跨儲存同步刪除邏輯（DynamoDB + S3 + OpenSearch）
    - _需求：H03.1, H03.2, H03.3_

- [x] 23. 實作報表與語音摘要
  - [x] 23.1 實作長者日週年報表
    - 實作一週與一年時間範圍的生活紀錄彙整（睡眠、飲食、作息、使用狀況）
    - 實作視覺化報表資料格式
    - 實作語音詢問報表時的語音摘要回覆
    - 僅呈現已擷取且經 Schema 驗證的事件資料
    - _需求：A07.1, A07.2, A07.3, A07.4_

- [x] 24. 實作展示資料與去識別化
  - [x] 24.1 建立虛擬展示資料
    - 建立虛擬 Persona（林阿嬤等）與模擬對話資料
    - 建立模擬事件、記憶、摘要資料
    - 撰寫 README 說明去識別化方式與資料產生方法
    - 確保不使用真實個資
    - _需求：H05.1, H05.2, H05.3_

- [x] 25. 端到端整合與 Demo 流程驗證
  - [x] 25.1 串接完整語音互動流程
    - 連接 PWA → WebSocket → Router → Step Functions → ASR → Context → LLM → Guardrail → TTS → 播放（全部節點皆為真實 Lambda，`cdk synth` 成功打包並串接，非 stub）
    - 端到端延遲 < 5 秒：無法在本環境對已部署系統實測（無 AWS 帳號存取權），已透過各節點 timeout 預算與 property test 驗證重試/降級邏輯正確；建議部署後以真實流量量測
    - 驗證各節點失敗時的降級回應（ASL Catch → Pass 狀態回傳 DEGRADATION_STRATEGIES 對應訊息，經 workflow property test 覆蓋）
    - _需求：A01.1, A01.2, J01.1_

  - [x] 25.2 驗證 Demo 必演流程
    - 林阿嬤臺語對話：demo seed data（scripts/seed-demo-data.ts）＋ ASR/TTS 對 nan-TW 皆路由至 SageMaker（測試覆蓋）
    - ASR 逐字稿顯示：ASL Respond 狀態回傳 transcript 欄位，前端 VoiceInteractionPanel 已顯示
    - 情境感知回覆（Persona、記憶、摘要注入）：context-handler.ts 串接 ContextComposer + data-provider，integration test 覆蓋
    - 結構化事件擷取：新增 post-processing-handler.ts，由 Router 在每輪對話後非同步觸發（design.md「par 非同步處理」），event-to-summary integration test 覆蓋
    - 確認式記憶流程：候選記憶產生同樣由 post-processing-handler.ts 觸發；確認/拒絕/檢索由照護者後台 UI 呼叫 REST API 完成，memory-to-context integration test 覆蓋（語音端「詢問是否同意保存」之語音提示為 P1 加強項，尚未寫入 ASL）
    - 衛教 RAG 查詢（來源引用、排除過期文件）：search-to-answer integration test 覆蓋
    - 照護者後台操作（概覽、事件修正、記憶管理）：前端 dashboard 頁面已建置並可 build/serve
    - 家屬通知：notification 模組 + failure-notification integration test 覆蓋
    - _需求：全部 Demo 必演流程（實際真人 Demo 綵排需於部署後另行執行）_

  - [x]* 25.3 撰寫整合測試
    - 端到端語音對話整合測試（voice-pipeline.integration.test.ts）
    - 事件擷取與摘要整合測試（event-to-summary.integration.test.ts）
    - 記憶確認流程整合測試（memory-to-context.integration.test.ts）
    - 衛教 RAG 查詢整合測試（search-to-answer.integration.test.ts）
    - 連續失敗通知整合測試（failure-notification.integration.test.ts）
    - _需求：全部_

- [x] 26. 最終檢查點 - 確保所有測試通過並完成部署準備
  - 確保所有測試通過，如有問題請詢問使用者。（115/115 測試通過；`cdk synth` 成功產生 29 個 Lambda + 1 個 Step Functions 狀態機 + API Gateway REST/WebSocket + DynamoDB/S3/Cognito/KMS；前端 `next build` 成功。尚未執行 `cdk deploy`（無 AWS 帳號存取權）——部署與真實延遲/Demo 綵排需使用者另行於有權限環境執行。）

## 備註

- 標記 `*` 的任務為選擇性任務，可在 MVP 快速迭代中跳過
- 每個任務都引用了對應的需求編號以確保可追溯性
- 檢查點確保增量驗證，避免問題累積
- Property Tests 驗證跨所有輸入的通用正確性特性
- 單元測試驗證特定場景與邊界條件
- 實作語言為 TypeScript，測試框架為 Vitest + fast-check
- 基礎架構使用 AWS CDK 或 SAM 定義

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4"] },
    { "id": 2, "tasks": ["2.1", "2.2"] },
    { "id": 3, "tasks": ["2.3", "2.4"] },
    { "id": 4, "tasks": ["4.1", "4.2", "4.3"] },
    { "id": 5, "tasks": ["4.4", "4.5", "4.6", "5.1"] },
    { "id": 6, "tasks": ["5.2", "5.3", "5.4"] },
    { "id": 7, "tasks": ["6.1", "6.2", "7.1"] },
    { "id": 8, "tasks": ["6.3", "6.4", "7.2", "7.3", "8.1"] },
    { "id": 9, "tasks": ["10.1", "11.1"] },
    { "id": 10, "tasks": ["10.2", "10.3", "10.4", "11.2"] },
    { "id": 11, "tasks": ["11.3", "11.4", "11.5", "11.6", "12.1"] },
    { "id": 12, "tasks": ["12.2", "14.1"] },
    { "id": 13, "tasks": ["14.2", "15.1"] },
    { "id": 14, "tasks": ["14.3", "14.4", "14.5", "14.6"] },
    { "id": 15, "tasks": ["14.7", "16.1"] },
    { "id": 16, "tasks": ["16.2", "18.1", "18.2", "18.3"] },
    { "id": 17, "tasks": ["19.1", "19.2", "19.3", "19.4"] },
    { "id": 18, "tasks": ["20.1", "20.2", "20.3", "20.4"] },
    { "id": 19, "tasks": ["22.1", "23.1", "24.1"] },
    { "id": 20, "tasks": ["25.1", "25.2"] },
    { "id": 21, "tasks": ["25.3"] }
  ]
}
```
