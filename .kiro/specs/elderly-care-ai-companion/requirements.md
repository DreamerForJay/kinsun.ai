# 需求文件：智慧長照 AI 陪伴系統

> **LEGACY SPEC。** 本文件描述的舊 TypeScript／Lambda／Step Functions／DynamoDB 方案已由 [ADR 0007](../../../docs/adr/0007-canonical-backend-and-aws-deployment-authority.md) 取代，不是目前實作或進度權威來源，也不得用來宣告 Gate 1 完成。現況以 repository 根目錄 [`AGENTS.md`](../../../AGENTS.md)、canonical `docs/` 規格與可執行 `contracts/` 為準；歷史完成清單見 [`tasks.legacy.md`](tasks.legacy.md)。

## 簡介

智慧長照 AI 陪伴系統是一套以語音優先為核心設計原則的長者照護輔助平台。系統透過自動語音辨識（ASR）、大型語言模型（Bedrock）與語音合成（TTS）技術，為偏鄉、獨居或日照場域中的長者提供自然語言互動陪伴。系統自動擷取生活資訊、產生每日摘要、支援確認式長期記憶、提供衛教知識檢索，並讓照護者與家屬透過後台掌握長者近況。

## 產品原則

- 語音優先：長者不必打字，也不必理解複雜選單
- 人機協作：AI 協助記錄與整理，不取代照護者與醫療專業
- 確認後記憶：可能影響未來互動的個人資訊，經確認後才成為長期記憶
- 可追溯：摘要、衛教回答與提醒應能回溯至原始事件或可信來源
- 最小必要資料：只蒐集完成服務所需的資料，並提供更正與刪除方式
- 安全優先：不提供診斷、停藥、改藥或治療決策

## 詞彙表

- **System（系統）**：智慧長照 AI 陪伴系統整體
- **ASR_Engine（語音辨識引擎）**：負責將長者語音轉為文字的元件，整合 AWS Transcribe 或預部署之 SageMaker Endpoint
- **TTS_Engine（語音合成引擎）**：負責將文字回覆轉為語音播放的元件
- **LLM_Engine（大型語言模型引擎）**：AWS Bedrock 提供的對話生成元件
- **Context_Composer（情境組合器）**：負責動態組成提示詞（Prompt）之元件
- **Event_Extractor（事件擷取器）**：從對話中擷取結構化生活事件的元件
- **Memory_Manager（記憶管理器）**：管理候選記憶產生、確認、檢索與刪除的元件
- **Summary_Generator（摘要產生器）**：每日自動產生長者生活摘要的元件
- **Search_Engine（搜尋引擎）**：整合 BM25 與向量搜尋的衛教知識檢索元件
- **Reranker（重排序器）**：對搜尋結果進行重新排序的元件
- **Notification_Service（通知服務）**：負責傳送摘要與警示給家屬的元件
- **Guardrail_Engine（護欄引擎）**：Bedrock Guardrails 攔截不安全內容的元件
- **Workflow_Orchestrator（工作流協調器）**：API Gateway + Lambda + Step Functions 協調各節點的元件
- **Elder（長者）**：系統主要使用者，透過語音與系統互動
- **Caregiver（照護者／照服員）**：負責照護長者並使用後台管理介面的人員
- **Family_Member（家屬）**：接收長者近況通知的相關人員
- **PWA**：Progressive Web App，系統前端應用程式
- **Persona**：為每位長者設定的個人化互動風格，包含語言偏好、稱呼與回覆長度
- **Confirmed_Memory（已確認記憶）**：經長者或照護者確認後保存的長期記憶
- **Candidate_Memory（候選記憶）**：尚未經確認的記憶候選項目
- **Knowledge_Base（知識庫）**：經審查的衛教文件索引庫

## 需求

---

### EPIC A｜長者語音互動陪伴

---

### 需求 A01：低操作負擔的語音入口

**使用者故事：** 身為長者，我希望只需一個簡單動作就能開始語音互動，以便在數位操作能力有限的情況下仍能使用系統。

#### 驗收條件

1. THE PWA SHALL 在首頁顯示一個主要操作按鈕供 Elder 開始錄音
2. WHEN Elder 按下錄音按鈕，THE System SHALL 透過視覺動畫與語音提示指示目前錄音狀態（等待中、錄音中、處理中、播放中）
3. WHEN PWA 偵測到麥克風權限未授予，THE System SHALL 以白話文字與語音引導 Elder 授予麥克風權限
4. THE PWA SHALL 支援行動裝置瀏覽器與桌面瀏覽器之跨裝置使用
5. WHEN System 偵測到連續三次語音互動失敗，THE Notification_Service SHALL 發送異常通知給已設定之 Caregiver 或 Family_Member

---

### 需求 A02：多語言語音辨識（國語、臺語、客語、英語與混語）

**使用者故事：** 身為長者，我希望用自己習慣的語言（國語、臺語、客語、英語或混語）說話就能被系統理解，以便自然地與系統互動。

#### 驗收條件

1. WHEN Elder 開始語音輸入，THE ASR_Engine SHALL 自動判斷語言並將語音傳送至對應之 ASR 服務（AWS Transcribe 或預部署之 SageMaker Endpoint）進行辨識
2. WHEN ASR_Engine 辨識信心分數低於設定閾值，THE System SHALL 以語音請 Elder 再說一次
3. THE ASR_Engine SHALL 支援國語、臺語、客語、英語以及混語之辨識
4. THE System SHALL 保留每次辨識所使用的服務端點、模型版本與辨識耗時於日誌中
5. IF ASR 服務回應逾時或發生錯誤，THEN THE System SHALL 執行重試策略並於重試失敗後通知 Elder 稍後再試

---

### 需求 A03：符合語言偏好的語音回覆

**使用者故事：** 身為長者，我希望系統用我偏好的語言與稱呼方式回覆我，以便感到親切與自然。

#### 驗收條件

1. THE LLM_Engine SHALL 依據 Elder 之 Persona 設定（語言偏好、稱呼、回覆長度）產生回覆文字
2. WHEN Persona 語言設定為國語，THE TTS_Engine SHALL 使用 Amazon Polly 產生語音回覆
3. WHEN Persona 語言設定為臺語或客語，THE TTS_Engine SHALL 使用已驗證之臺語或客語 TTS 模型產生語音回覆
4. IF TTS_Engine 產生語音失敗，THEN THE System SHALL 以文字形式顯示回覆內容於畫面上

---

### 需求 A04：情境感知對話

**使用者故事：** 身為長者，我希望系統記得我的近況與偏好來回應我，以便對話更貼近我的生活而非制式回答。

#### 驗收條件

1. WHEN 產生對話回覆，THE Context_Composer SHALL 動態注入相關時間、天氣、近期摘要與 Confirmed_Memory 至提示詞中
2. THE LLM_Engine SHALL 僅將 Confirmed_Memory 作為已知事實使用，Candidate_Memory 不得作為事實引用
3. WHEN 無相關資料可供參考，THE LLM_Engine SHALL 誠實表達不知道，不得虛構資訊

---

### 需求 A05：對話失敗的安全降級

**使用者故事：** 身為長者，我希望系統即使遇到技術問題也能給我明確回應，以便我不會困惑於無回應的狀態。

#### 驗收條件

1. WHEN ASR_Engine 或 LLM_Engine 或 TTS_Engine 回應逾時超過設定時限，THE System SHALL 以預錄語音或固定文字提示 Elder 稍後再試
2. THE System SHALL 對同一次互動中的重試次數設定上限，不得無限重試
3. WHEN 對話元件發生錯誤，THE System SHALL 將錯誤類型、時間戳記與 trace ID 寫入 CloudWatch 日誌

---

### 需求 A06：錄音與資料使用同意

**使用者故事：** 身為長者，我希望清楚知道系統錄音的用途與保存方式，並能隨時撤回同意，以便我對自己的資料有掌控權。

#### 驗收條件

1. WHEN Elder 首次使用系統，THE System SHALL 以白話文字與語音說明錄音內容、保存期限與刪除方式
2. WHEN Elder 未授予錄音同意，THE System SHALL 不啟動麥克風且不保存任何語音資料
3. THE System SHALL 提供 Elder 隨時撤回錄音同意之功能
4. WHEN Elder 撤回同意，THE System SHALL 停止後續錄音並依保留政策處理既有資料

---

### 需求 A07：長者日週年報表

**使用者故事：** 身為長者，我希望能回顧自己一週或一年的生活紀錄（睡眠、飲食、作息、使用狀況），以便了解自身生活型態的變化。

#### 驗收條件

1. THE System SHALL 提供一週與一年時間範圍之生活紀錄報表，涵蓋睡眠、飲食、作息與系統使用狀況
2. THE System SHALL 同時支援視覺化報表與語音摘要兩種呈現方式
3. WHEN Elder 以語音詢問生活紀錄，THE System SHALL 以語音回覆對應時間範圍之摘要
4. THE System SHALL 僅呈現已擷取且經 Schema 驗證之事件資料於報表中

---

### EPIC B｜生活記錄與每日摘要

---

### 需求 B01：自動擷取生活資訊

**使用者故事：** 身為照護者，我希望系統自動從對話中擷取長者的飲食、活動、睡眠、用藥與重要事件，以便我不需逐一記錄。

#### 驗收條件

1. WHEN 對話結束，THE Event_Extractor SHALL 從對話內容中擷取飲食、活動、睡眠、用藥陳述、情緒與重要事件
2. THE Event_Extractor SHALL 以 JSON Schema 驗證擷取結果後寫入 DynamoDB
3. THE Event_Extractor SHALL 對用藥相關內容僅記錄 Elder 之原始陳述，不得推論用藥遵從度或效果
4. THE Event_Extractor SHALL 為每筆事件保留日期、事件類型、原始對話片段、信心分數與來源對話 ID
5. WHEN Event_Extractor 對擷取結果信心不足，THE Event_Extractor SHALL 將該事件標記為 needs_review 狀態

---

### 需求 B02：每日 AI 摘要

**使用者故事：** 身為照護者，我希望每天收到系統自動產生的長者生活摘要，以便快速掌握長者近況而不必閱讀所有對話紀錄。

#### 驗收條件

1. THE Summary_Generator SHALL 由 EventBridge 於每日固定時間觸發執行
2. THE Summary_Generator SHALL 涵蓋飲食、活動、睡眠、用藥陳述與重要事件等面向
3. THE Summary_Generator SHALL 為摘要中每項內容標註對應之原始事件 ID，供 Caregiver 回查
4. THE Summary_Generator SHALL 不新增原始事件中不存在的診斷或醫療判斷

---

### 需求 B03：照護者修正與覆核

**使用者故事：** 身為照護者，我希望能修正系統擷取的事件內容，以便確保長者紀錄的正確性。

#### 驗收條件

1. THE System SHALL 允許 Caregiver 編輯事件之內容、類型與 review_status
2. WHEN Caregiver 修改事件，THE System SHALL 保存修正前後之值與修正時間
3. THE Summary_Generator SHALL 於後續摘要中優先使用 Caregiver 已確認之事件資料
4. THE System SHALL 保留 Caregiver 修正紀錄，供後續模型評估使用

---

### 需求 B04：事件時間軸（P1）

**使用者故事：** 身為照護者，我希望能依時間、類型或審查狀態篩選長者的事件紀錄，以便快速找到特定時段的資訊提供給醫生。

#### 驗收條件

1. THE System SHALL 提供依日期範圍、事件類型與審查狀態篩選事件之功能
2. THE System SHALL 不重複顯示相同事件
3. THE System SHALL 為每筆事件提供連結回溯至原始對話片段
4. THE System SHALL 支援依時間範圍搜尋事件以供醫療人員查閱

---

### EPIC C｜照護者與家屬介面

---

### 需求 C01：多長者概覽

**使用者故事：** 身為照護者，我希望在單一畫面上看到所有負責長者的近況摘要，以便快速判斷誰需要優先關注。

#### 驗收條件

1. THE System SHALL 為 Caregiver 顯示每位 Elder 之最後互動時間、今日互動次數、摘要狀態與待覆核事件數
2. THE System SHALL 僅顯示該 Caregiver 具有權限之 Elder 資料
3. THE System SHALL 不使用未經專業定義之風險診斷標籤（如「高風險」「異常」），僅呈現客觀數據

---

### 需求 C02：長者詳情頁

**使用者故事：** 身為照護者，我希望能查看單一長者的完整資訊（基本資料、AI 擷取事件、已確認記憶、衛教內容），以便全面了解該長者狀況。

#### 驗收條件

1. THE System SHALL 將 Elder 詳情頁區分為基本資料、AI 擷取事件、Confirmed_Memory 與衛教內容等區塊
2. THE System SHALL 依角色權限對敏感欄位進行遮罩處理
3. THE System SHALL 為每項資料顯示更新時間與資料來源

---

### 需求 C03：家屬摘要通知（P1）

**使用者故事：** 身為家屬，我希望定期收到長者的適量近況摘要，以便在無法每天陪伴時仍能了解長者生活而不感到恐慌。

#### 驗收條件

1. THE Notification_Service SHALL 允許 Family_Member 設定通知頻率、通知通路與靜默時段
2. THE Notification_Service SHALL 僅包含必要且不造成過度恐慌之資訊於通知內容中
3. WHEN 系統偵測到符合明確定義之高風險規則的事件，THE Notification_Service SHALL 立即通知 Family_Member
4. THE System SHALL 提供 Family_Member 取消訂閱通知之功能

---

### EPIC D｜確認式 AI 長期記憶

---

### 需求 D01：產生候選記憶

**使用者故事：** 身為長者，我希望系統能記住我的穩定偏好與重要關係，以便日後對話更貼近我的生活。

#### 驗收條件

1. THE Memory_Manager SHALL 僅針對穩定偏好、重要關係與固定作息產生 Candidate_Memory
2. THE Memory_Manager SHALL 不將閒聊內容或敏感推測轉為 Candidate_Memory
3. THE Memory_Manager SHALL 為每筆 Candidate_Memory 記錄來源對話 ID、建立時間與信心分數

---

### 需求 D02：確認後才保存

**使用者故事：** 身為長者，我希望系統在記住我的資訊前先詢問我的同意，以便我對自己的記憶資料有掌控權。

#### 驗收條件

1. WHEN Memory_Manager 產生 Candidate_Memory，THE System SHALL 以簡短語音問題詢問 Elder 是否同意保存
2. WHEN Elder 拒絕保存，THE Memory_Manager SHALL 不將該 Candidate_Memory 寫入長期記憶儲存
3. THE System SHALL 允許 Caregiver 在後台確認、修正或拒絕 Candidate_Memory
4. THE Memory_Manager SHALL 為每筆 Confirmed_Memory 記錄確認者身份與確認時間

---

### 需求 D03：記憶檢索與個人化回應

**使用者故事：** 身為長者，我希望系統能在適當時機引用我的記憶來回應我，以便對話更自然且個人化。

#### 驗收條件

1. WHEN 產生對話回覆，THE Memory_Manager SHALL 僅檢索與當前對話上下文相關之少量 Confirmed_Memory
2. THE Memory_Manager SHALL 嚴格以 elder_id 隔離記憶資料，禁止跨使用者資料存取
3. WHEN 檢索到之 Confirmed_Memory 與當前對話內容產生衝突，THE System SHALL 以語音詢問 Elder 確認正確資訊

---

### 需求 D04：更正與刪除記憶

**使用者故事：** 身為長者，我希望能檢視、更正或刪除系統記住的資訊，以便確保記憶資料的正確性與我的隱私。

#### 驗收條件

1. THE System SHALL 提供 Elder 與 Caregiver 檢視、更正、停用與刪除 Confirmed_Memory 之功能
2. WHEN Confirmed_Memory 被刪除，THE Memory_Manager SHALL 確保該記憶不再被後續檢索引用
3. THE System SHALL 保存記憶變更之稽核紀錄，並依資料保留政策於到期後刪除稽核紀錄

---

### EPIC E｜搜尋引擎、RAG 與衛教知識

---

### 需求 E01：自然語言查詢理解

**使用者故事：** 身為長者，我希望用口語化的方式問健康問題就能得到回答，以便不需學習特定問法。

#### 驗收條件

1. WHEN Elder 以口語提出健康相關問題，THE Search_Engine SHALL 將口語問題轉換為可檢索查詢並保留原始問題
2. THE Search_Engine SHALL 不改變原始問題中的關鍵醫療條件或限定範圍
3. WHEN Search_Engine 無法確認 Elder 之查詢意圖，THE System SHALL 以語音向 Elder 澄清問題
4. WHEN Search_Engine 檢索無相關結果，THE LLM_Engine SHALL 回覆不知道，不得自行補完答案

---

### 需求 E02：Metadata Filtering

**使用者故事：** 身為系統管理者，我希望搜尋引擎能依文件屬性（來源機關、服務類型、地區、生效日期、風險等級、審查狀態）過濾結果，以便確保回答品質。

#### 驗收條件

1. THE Search_Engine SHALL 支援以 source_agency、service_type、region、effective_date、risk_level 與 review_status 進行檢索前過濾
2. THE Search_Engine SHALL 不將 review_status 為 needs_review 之文件以已驗證資料呈現給使用者
3. THE Search_Engine SHALL 不將已失效之文件排入主要答案結果中

---

### 需求 E03：Hybrid Search

**使用者故事：** 身為系統管理者，我希望搜尋引擎同時使用關鍵字比對與語意向量搜尋，以便提升檢索的召回率與精準度。

#### 驗收條件

1. THE Search_Engine SHALL 同時執行 BM25 關鍵字搜尋與 Vector KNN 語意搜尋
2. THE Search_Engine SHALL 合併兩種搜尋結果並去除重複項目，同時保留各結果之來源分數
3. THE Search_Engine SHALL 具備可量化比較之測試集以評估搜尋指標

---

### 需求 E04：Reranker 重新排序

**使用者故事：** 身為系統管理者，我希望搜尋結果經過重新排序以考量多重因素，以便將最相關且可信的內容優先呈現。

#### 驗收條件

1. THE Reranker SHALL 依據查詢相關度、來源可信度、Persona 適用度、文件日期與審查狀態對搜尋結果進行重新排序
2. THE Reranker SHALL 僅將排序後前 N 筆結果送入 LLM_Engine 作為回答依據
3. THE Reranker SHALL 記錄排序依據與結果順序以供後續重現與評估

---

### 需求 E05：有根據的衛教回答

**使用者故事：** 身為長者，我希望系統回答健康問題時能告訴我資訊來源，以便我知道答案是可信的。

#### 驗收條件

1. WHEN LLM_Engine 回答衛教問題，THE System SHALL 顯示來源文件名稱與發布機關
2. WHEN 知識庫中資料不足以回答問題，THE LLM_Engine SHALL 明確說明資訊不足，不得自行補完或虛構內容
3. THE System SHALL 於衛教回答中標示「僅供參考，不作為醫療診斷依據」

---

### 需求 E06：搜尋品質評估（P1）

**使用者故事：** 身為系統管理者，我希望能量化評估搜尋品質，以便持續改善搜尋效果。

#### 驗收條件

1. THE System SHALL 維護人工標註之搜尋品質測試集
2. THE System SHALL 支援比較不同搜尋方法之 Recall@K、MRR 與 NDCG@K 指標
3. THE System SHALL 提供使用者對 AI 對話回答之評分功能以蒐集回饋

---

### EPIC F｜個人化推薦與下一步行動

---

### 需求 F01：個人化關懷主題排序（P1）

**使用者故事：** 身為長者，我希望系統主動提出適合我的關懷話題，以便對話更有溫度且不重複。

#### 驗收條件

1. THE System SHALL 從近期事件、Confirmed_Memory、時間因素與 Elder 偏好中產生候選關懷主題
2. THE System SHALL 不以敏感推測（如未確認之健康狀況）作為推薦依據
3. WHEN Elder 拒絕某關懷主題，THE System SHALL 降低該主題後續出現之頻率

---

### 需求 F02：照護者待辦建議（P1）

**使用者故事：** 身為照護者，我希望系統建議我需要執行的待辦事項，以便不遺漏重要的照護行動。

#### 驗收條件

1. THE System SHALL 僅建議查看、確認、聯繫與追蹤等待辦類型
2. THE System SHALL 不建議改藥、停藥或醫療診斷相關之行動
3. THE System SHALL 為每項待辦建議顯示產生原因與對應之原始事件

---

### EPIC G｜資料治理與知識庫 ETL

---

### 需求 G01：可信來源登錄

**使用者故事：** 身為內容管理者，我希望每份進入知識庫的文件都有完整來源資訊，以便確保資料可信度與可追溯性。

#### 驗收條件

1. THE System SHALL 為每份文件建立 manifest，記錄來源機關、標題、版本、適用地區與授權資訊
2. THE System SHALL 拒絕無來源資訊之文件進入 Knowledge_Base

---

### 需求 G02：文件切片與審查

**使用者故事：** 身為內容管理者，我希望文件經過標準化流程處理後才進入索引，以便確保搜尋品質與資料一致性。

#### 驗收條件

1. THE System SHALL 依序執行來源登錄、解析清理、結構化記錄、Chunk JSONL 產生、Metadata 標註、人工審查與 Embedding/Index 建立之流程
2. THE System SHALL 將新匯入之資料預設為 needs_review 狀態，待審查通過後方可作為已驗證資料使用

---

### 需求 G03：版本與失效管理（P1）

**使用者故事：** 身為內容管理者，我希望能追溯每個 Chunk 的來源版本並管理文件失效，以便確保使用者不會收到過期資訊。

#### 驗收條件

1. THE System SHALL 為每個 Chunk 記錄對應之來源文件版本
2. THE System SHALL 支援重建索引並標記舊版文件為失效狀態
3. THE Search_Engine SHALL 預設排除已失效之文件於搜尋結果中

---

### EPIC H｜安全、隱私與醫療邊界

---

### 需求 H01：角色權限與資料隔離

**使用者故事：** 身為系統管理者，我希望不同角色只能存取其權限範圍內的資料，以便確保長者隱私不被未授權存取。

#### 驗收條件

1. THE System SHALL 使用 Amazon Cognito 搭配 IAM 角色實施角色權限控制
2. THE System SHALL 在 DynamoDB、S3 與記憶索引中以 elder_id 與 tenant_id 實施資料隔離
3. THE System SHALL 禁止任何角色跨 Elder 存取資料，包含 API 層與資料層

---

### 需求 H02：傳輸與儲存保護

**使用者故事：** 身為系統管理者，我希望所有資料在傳輸與儲存時都受到加密保護，以便符合資料安全要求。

#### 驗收條件

1. THE System SHALL 使用 HTTPS 加密所有網路傳輸
2. THE System SHALL 使用 AWS KMS 加密所有靜態儲存資料
3. THE System SHALL 不將加密金鑰硬編碼於程式碼或組態檔中

---

### 需求 H03：資料保留與刪除

**使用者故事：** 身為系統管理者，我希望各類資料有明確的保存期限與自動刪除機制，以便符合最小必要資料原則。

#### 驗收條件

1. THE System SHALL 為各類資料（語音檔、對話紀錄、事件、記憶、摘要、稽核紀錄）定義明確之保存期限
2. THE System SHALL 使用 S3 Lifecycle Policy 於保存期限到期後自動刪除對應資料
3. WHEN 資料刪除觸發，THE System SHALL 同步處理所有儲存位置（S3、DynamoDB、索引）中的對應資料

---

### 需求 H04：醫療安全護欄

**使用者故事：** 身為長者，我希望系統不會給我錯誤的醫療建議，以便我的健康不會因系統回覆而受到危害。

#### 驗收條件

1. THE Guardrail_Engine SHALL 使用 Bedrock Guardrails 攔截包含診斷、停藥、改藥或治療決策之回覆內容
2. WHEN 對話內容涉及緊急狀況（如胸痛、跌倒、意識不清），THE System SHALL 回覆固定之安全指引（如撥打 119、聯繫家屬）
3. THE System SHALL 維護醫療安全護欄之測試案例集以驗證攔截效果

---

### 需求 H05：展示資料去識別化

**使用者故事：** 身為系統管理者，我希望展示與測試使用虛擬資料，以便不洩漏真實長者之個人資訊。

#### 驗收條件

1. THE System SHALL 使用虛擬 Persona 與模擬資料進行所有展示與測試
2. THE System SHALL 於 README 文件中說明去識別化方式與資料產生方法
3. THE System SHALL 不使用真實長者之個人資料進行任何公開展示

---

### EPIC J｜Workflow、可觀測性與可靠性

---

### 需求 J01：確定性工作流協調

**使用者故事：** 身為系統管理者，我希望系統各元件之間的協調由確定性工作流管理，以便錯誤處理與重試邏輯可預測且可追蹤。

#### 驗收條件

1. THE Workflow_Orchestrator SHALL 使用 API Gateway 搭配 Lambda 與 Step Functions 協調各處理節點
2. THE Workflow_Orchestrator SHALL 為每個節點定義輸入格式、輸出格式、逾時時限、重試策略與失敗處理方式
3. WHEN 工作流節點失敗且超過重試上限，THE Workflow_Orchestrator SHALL 執行預定義之降級處理

---

### 需求 J02：Context Engineering

**使用者故事：** 身為系統管理者，我希望系統能動態組合最相關的上下文送入 LLM，以便在 Token 限制內提供最佳對話品質。

#### 驗收條件

1. THE Context_Composer SHALL 動態組合 System Prompt、Persona、近期摘要、Confirmed_Memory、情境資訊與 Search_Engine 檢索結果
2. THE Context_Composer SHALL 根據 Token 預算選擇性納入上下文項目，不得將所有可用資料全部送入
3. THE Context_Composer SHALL 記錄每次對話實際使用之 context item 清單以供追溯

---

### 需求 J03：輸出驗證與 Guardrail

**使用者故事：** 身為系統管理者，我希望 AI 的每項輸出都經過結構與安全驗證，以便確保回覆品質與安全性。

#### 驗收條件

1. THE System SHALL 對結構化輸出（事件擷取、記憶候選）執行 JSON Schema 驗證
2. THE System SHALL 對對話回覆執行醫療安全、敏感資訊與內容適當性檢查
3. WHEN 輸出驗證失敗，THE System SHALL 依策略執行重試或降級回覆

---

### 需求 J04：監控與追蹤

**使用者故事：** 身為系統管理者，我希望能追蹤每次互動的完整處理路徑與各階段效能指標，以便快速診斷問題。

#### 驗收條件

1. THE System SHALL 將各處理階段之延遲、成功率與錯誤率寫入 CloudWatch Metrics
2. THE System SHALL 為每次互動產生共同 trace ID 以串聯各階段日誌
3. THE System SHALL 不將包含個人資訊之對話逐字稿寫入監控日誌
4. THE System SHALL 建立降級測試案例以驗證各元件故障時的系統行為

---

## 優先級定義

### P0 — 決賽前必須完成

語音入口、ASR 多語言辨識（整合既有服務）、Bedrock 對話、TTS 語音合成、生活事件擷取、Schema 驗證、每日摘要、照護者後台、資料追溯與修正、確認式記憶、Metadata Filtering / Hybrid Search / Reranker、Context Engineering、Guardrails、角色權限、同意與保留政策、搜尋實測評估、完整 Demo 與安全降級。

### P1 — 時間足夠再完成

事件時間軸、家屬推播通知、個人化關懷主題、照護者待辦排序、知識庫版本管理。

### 暫不列入

Learning to Rank 訓練、協同過濾推薦、Graph DB、複雜 Multi-agent 自主協商、模型並行與競價實例、從零訓練 CNN/Transformer、ASR 模型微調與訓練。

---

## Demo 必演流程

1. 林阿嬤臺語對話
2. ASR 逐字稿顯示
3. 情境感知回覆
4. 結構化事件擷取
5. 確認式記憶流程
6. 衛教 RAG 查詢
7. 照護者後台操作
8. 家屬通知

---

## Definition of Done

- 功能已部署至 AWS
- 具備正常、失敗與權限測試案例
- README 文件完整
- 不使用真實個資
- 不宣稱未實測數據
- 具備可追溯日誌
- 端到端使用者旅程完整可示範
