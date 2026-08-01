# 成員 D：ASR／TTS 與 Agent／RAG 整合交接

- 日期：2026-08-02
- 分支：`feature/member-d-speech-agent-gradio`
- 負責範圍：台語／客語 ASR、TTS 候選評估、SageMaker BYOC、Speech 整合工作台
- 資料限制：Demo、測試與截圖只能使用 Synthetic／完成去識別資料

## 1. 目前完成狀態

| 項目 | 狀態 | 可驗證證據 |
| --- | --- | --- |
| SageMaker ASR | 已部署並實際呼叫 | `kinsun-speech-asr-v1`，`us-west-2`，回傳 JSON |
| 台／客語 ASR 容器 | 已建立 | `services/speech-gateway/sagemaker/Dockerfile.asr` |
| 低信心 Gate | 已實作於工作台 | `< 0.65` 或空逐字稿要求人工確認 |
| Core → Agent／RAG 串接 | 已依現行 contract 實作 client | 工作台只呼叫 Core companion-turn，不直連 Agent |
| Gradio 工作台 | 已實作並做瀏覽器 smoke test | `evals/speech/speech_workbench.py` |
| 外部台／客語 TTS 評估 | Synthetic 實測成功 | `evals/speech/evaluate_external_tts.py` |
| SageMaker TTS | `Dockerfile.tts` 已固定模型 revision，Endpoint 尚未部署 | 仍需授權決策、image build 與 AWS 實測 |
| 正式前端語音串流 | 尚未實作 | 目前 Core response 仍是 `TEXT_ONLY` |

## 2. 正式資料流

```text
錄音／上傳
  → SageMaker ASR
  → { text, confidence }
  → confidence < 0.65 或空結果？
      → 是：人工修正與確認，禁止送 Agent
      → 否：仍允許人工修正
  → Core API /api/v1/voice-sessions/{session_id}/companion-turns
  → Core 重新驗證 Authorization／Tenant／Elder／Consent／Session
  → Agent Runtime（需要時執行受控 RAG）
  → reply_text + safety／trace metadata
  → SageMaker TTS（待部署）或明確文字降級
```

不要讓 Speech Gateway 直接呼叫 Agent Runtime。`actor_id`、`tenant_id`、`elder_id`
不能由 Gradio 或模型自報；Core 是唯一正式 Gate。

## 3. 啟動 Gradio 工作台

```powershell
uv venv .\evals\speech\.venv --python 3.10
uv pip install --python .\evals\speech\.venv\Scripts\python.exe `
  -r .\evals\speech\requirements-workbench.txt

$env:AWS_DEFAULT_REGION = "us-west-2"
$env:KINSUN_ASR_ENDPOINT = "kinsun-speech-asr-v1"
$env:KINSUN_TTS_ENDPOINT = "kinsun-speech-tts-v1" # 尚未部署時只顯示設定，不呼叫
$env:KINSUN_CORE_API_URL = "http://127.0.0.1:8000"
$env:KINSUN_ASR_CONFIRM_THRESHOLD = "0.65"
$env:GRADIO_SERVER_PORT = "7861"

.\evals\speech\.venv\Scripts\python.exe .\evals\speech\speech_workbench.py
```

開啟 `http://127.0.0.1:7861`。程式固定綁定 `127.0.0.1` 且 `share=False`，禁止
為方便 Demo 改成公開分享連結。

## 4. 工作台操作順序

1. 先在「ASR 與低信心確認」上傳 Synthetic 音訊或使用 Mock。
2. 檢查逐字稿、confidence、模型版本與延遲。
3. 修正逐字稿並勾選「我已人工確認」。
4. 事先由 Core 建立已授權 Voice Session；填入 Session UUID 與短效 Bearer Token。
5. 在「Core → Agent／RAG」執行 companion turn。
6. 檢查 `result_status`、`safety_decision`、`risk_level`、`reason_codes` 與 trace。
7. 將安全回覆複製到 TTS 分頁。
8. 正式內容只可呼叫私有 SageMaker TTS；外部 Space 僅允許 Synthetic 文字。

Bearer Token 只存在當次 Gradio component 記憶體，不寫入報告、Git 或一般 Log。

## 5. ASR SageMaker 契約

請求：

- Content-Type：`application/octet-stream`
- Body：16 kHz／mono／signed 16-bit little-endian PCM
- CustomAttributes：`{"language":"nan-TW","sampleRate":16000}`

回應：

```json
{
  "text": "模型逐字稿",
  "confidence": 0.72
}
```

部署資源：

- Region：`us-west-2`
- ECR：`kinsun-speech-gateway`
- Model：`kinsun-speech-asr-v1`
- Endpoint Config：`kinsun-speech-asr-config-v1`
- Endpoint：`kinsun-speech-asr-v1`
- Instance：`ml.g4dn.xlarge`
- 模型：`adi-gov-tw/Taiwan-Tongues-ASR-CE-v2.0`
- Revision：`853363cf70e50d9771497a1c5dc88bf17f687f30`

底層模型支援 `zh`、`nan`、`hak`、`en`、`id`，但這個 endpoint contract 只接受
`nan-TW` 與 `hak-TW`。華語／英語在目標路由走 AWS Transcribe。Gradio 預設選台語不代表
模型或 endpoint 只有台語；同一下拉選單可切換客語。

既有本機 benchmark：台語 Micro CER 76.9%、客語 Micro CER 32.3%。兩者都未達可自動
信任的程度，尤其客語 Micro WER 仍達 91.7%，所以低信心／空結果人工確認 Gate 不得移除。
SageMaker 目前只以 Synthetic silence 驗證 wire compatibility，不能當品質證據。

## 6. Core／Agent 交接契約

工作台呼叫：

```http
POST /api/v1/voice-sessions/{session_id}/companion-turns
Authorization: Bearer <short-lived-token>
Idempotency-Key: speech-<uuid>
X-Correlation-ID: <uuid>
Content-Type: application/json

{"input_text":"已人工確認的逐字稿"}
```

只使用 Core 回傳 envelope 的 `data.reply_text` 做 TTS。若 `result_status` 是
`BLOCKED` 或 `SAFE_FALLBACK`，仍應朗讀 Core 提供的安全替代文字；不得改用原模型輸出。

RAG 的成功與否由 Agent Runtime 現行邏輯決定。沒有足夠來源或 provider 未設定時，
必須保留 `SAFE_FALLBACK`，Speech 不得自行補答案。

## 7. TTS 候選與限制

| 語言 | 候選 | Synthetic 實測 | 限制 |
| --- | --- | --- | --- |
| 客語 | `ivanusto/tw-hakka-tts` | 成功；可回傳斷詞、拼音、WAV | 第三方；底層模型授權待 Owner 確認 |
| 台語 | `tbdavid2019/Taiwanese-tts` model6 | 成功；可回傳台羅、WAV | 轉送外部 API且保留歷史，不得傳正式內容 |
| 台語 | `facebook/mms-tts-nan` | 漢字 tokenizer 已知不適用 | 非商用候選，不作正式選擇 |
| 客語 | VoxHakka／YourTTS | 容器骨架存在 | 非商用候選，正式部署前需授權決策 |

外部 TTS 腳本與工作台都要求明確 Synthetic 確認。不得使用客製語者錄音，因為聲紋
屬競賽禁止匯入的生物識別資料。

## 8. 測試

```powershell
.\evals\speech\.venv\Scripts\python.exe -m pytest .\evals\speech\tests -q

cd services/agent-runtime
uv sync --extra test --extra dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

另外必須執行：

```powershell
docker compose config --quiet
git diff --check
git status --short
```

## 9. 下一位接手者的工作

1. 取得 Owner 對台語／客語 TTS 模型與授權的明確決策。
2. 固定 TTS 模型 revision、建置並掃描容器。
3. 建立私有 `kinsun-speech-tts-v1` SageMaker Model／Config／Endpoint。
4. 使用 Synthetic 句子實際 invoke，驗證 WAV、延遲與文字降級。
5. 前端補 Voice transport；目前 Core contract 明確回傳 `TEXT_ONLY`。
6. 建立母語者盲測表，才可宣稱台語／客語 TTS 品質通過。

## 10. 回退與資源管理

- ASR 失敗或 timeout：回傳重試／請使用者重說，不送 Agent。
- TTS 失敗：顯示 `reply_text`，不得假裝已有音訊。
- Agent／RAG 失敗：使用 Core 的安全 fallback，不由 Speech 猜測。
- 不使用時刪除 SageMaker Endpoint 以停止 instance 持續占用；Model 與 ECR image 可保留重建。
- 不建立公開 S3、公開 Security Group 或公開 Gradio share URL。
