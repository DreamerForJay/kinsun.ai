# SageMaker endpoint 契約 + 部署步驟

## 為什麼是這個格式：直接讀 adapter 原始碼得到的，不是設計出來的

`packages/backend/src/asr/adapters.ts` 的 `SageMakerAdapter` 跟
`packages/backend/src/tts/adapters.ts` 的 `SageMakerTtsAdapter` 已經寫死了呼叫
方式，這個 endpoint 沒有自己重新設計格式的空間，必須完全符合下面這兩份契約。

### ASR：`nan-TW` / `hak-TW`

Backend 端送出（`asr/adapters.ts` 的 `SageMakerAdapter.transcribe`）：

```
InvokeEndpointCommand({
  EndpointName: process.env.ASR_SAGEMAKER_ENDPOINT,
  ContentType: 'application/octet-stream',
  Body: <原始音訊 bytes，PCM 或 opus，不是包 WAV header 的檔案>,
  CustomAttributes: JSON.stringify({ language, sampleRate }),  // language: 'nan-TW' | 'hak-TW'
})
```

Endpoint 必須回傳（JSON body）：

```json
{ "text": "轉寫結果", "confidence": 0.0 }
```

`confidence` 缺值時 backend 會當成 `0`（不會報錯，但信心分數全部變 0 會影響上游
guardrail/確認流程判斷，能給真實數字就給）。回應的 `CustomAttributes`（可選）會被
backend 存成 `modelVersion`，沒有就存 `'unknown'`。

**重點：輸入是 raw PCM/opus bytes，不是 WAV 檔案。** PoC 現有的
`core/speech_adapters.py` 是吃 WAV 檔案上傳（`voice_server.py` 的 `/api/asr`），
两者不一樣，這是唯一需要新寫的轉換邏輯（`inference_asr.py` 的 `input_fn`）：
用 `sampleRate`（`CustomAttributes` 給的）把 raw bytes 轉成 float32 numpy 陣列
餵進既有的 ASR pipeline。

### TTS：`nan-TW` / `hak-TW`

Backend 端送出（`tts/adapters.ts` 的 `SageMakerTtsAdapter.synthesize`）：

```
InvokeEndpointCommand({
  EndpointName: process.env.TTS_SAGEMAKER_ENDPOINT,
  ContentType: 'application/json',
  Body: JSON.stringify({ text, language, speakingSpeed }),
  // language: 'nan-TW' | 'hak-TW'
  // speakingSpeed: 'slow' | 'normal' | 'fast'
})
```

Endpoint 必須回傳：原始音訊 bytes 當 response body，`ContentType` header（沒帶的話
backend 預設當 `audio/wav`）。

### Adapter 拋錯時會發生什麼事（重要：不用擔心單一語言模型失敗會拖垮整個對話）

`tts/types.ts` 的 `TtsOutcome` 明確設計成「`synthesize()` 對呼叫端來說永遠不拋錯，
失敗時降級成純文字」（`degraded: true` + `textFallback`）。也就是說：如果
endpoint 對某個請求回錯誤（例如 nan TTS 目前那個漢字輸入會崩潰的已知 bug，見
`model-selection.md`），上層會自動接住、降級成文字，不會讓整個對話流程掛掉。
這代表 container 端不需要為了「絕對不能出錯」而做防禦性工程，把已知會失敗的
case 誠實地拋錯（回傳非 2xx 或讓 SageMaker 判定 invocation 失敗）即可，上層自然
會處理。

## 部署步驟（尚未在任何機器上執行過，`infra/`/`infrastructure/` 都沒有用 CDK 定義
這個 endpoint，目前是手動流程）

沿用 PoC repo `SAGEMAKER_SOP_與待辦清單.md` 的既有規劃，這裡只補上跟這次
container 骨架有關的步驟：

1. **建立 Notebook/EC2 環境**：GPU 用 `ml.g5.xlarge`（24GB）或以上，CPU-only 用
   `ml.m5.2xlarge`（32GB）。IAM Role 要有 ECR pull + S3 讀寫權限。
2. **Build + push BYOC image**（見 `../sagemaker/Dockerfile`）：
   ```bash
   aws ecr create-repository --repository-name speech-gateway-nan-hak
   docker build -t speech-gateway-nan-hak services/speech-gateway/sagemaker
   docker tag speech-gateway-nan-hak:latest <account>.dkr.ecr.<region>.amazonaws.com/speech-gateway-nan-hak:latest
   docker push <account>.dkr.ecr.<region>.amazonaws.com/speech-gateway-nan-hak:latest
   ```
   為什麼要 BYOC（自帶容器）而不是 SageMaker script mode：hak 的 TTS
   （VoxHakka）需要獨立 venv（`coqui-tts` 釘 `transformers<5`，跟 ASR 用的主環境
   不相容），單一 `requirements.txt` 沒辦法處理兩組互斥的依賴版本，只能在 image
   裡建兩個 Python 環境（沿用 PoC 既有的 subprocess 呼叫模式，見
   `../sagemaker/Dockerfile` 註解）。
3. **建立 Model / EndpointConfig / Endpoint**：ASR 跟 TTS 各自需要一個
   endpoint（`ASR_SAGEMAKER_ENDPOINT`、`TTS_SAGEMAKER_ENDPOINT` 是兩個獨立環境
   變數），可以用同一個 image、不同的 `SAGEMAKER_PROGRAM` 環境變數切換
   entrypoint（`inference_asr.py` vs `inference_tts.py`），或部署兩個獨立
   endpoint——後者比較簡單，先這樣做。
4. **把 endpoint 名稱填進 Lambda 環境變數**：`ASR_SAGEMAKER_ENDPOINT`/
   `TTS_SAGEMAKER_ENDPOINT`，對應 `infrastructure/lib/constructs/voice-workflow.ts`
   建的 ASR/TTS stage Lambda（目前這兩個 Lambda 已經有
   `sagemaker:InvokeEndpoint` IAM 權限，只是沒有 endpoint 可打）。
5. 部署完先用小樣本人工測試 ASR/TTS 各幾筆，確認契約真的對得上（尤其
   `CustomAttributes` 解析、raw PCM bytes 轉換這幾個新寫的邏輯），再讓 backend
   實際打。

**這台開發機器沒有 AWS 憑證**（`AGENTS.md` 已知問題 #7），上面 2-5 步都無法在這裡
實際執行/驗證，只完成了到步驟 2 的 image build（`docker build` 本機驗證過語法跟
依賴安裝，沒有 push 到 ECR），後續步驟需要在有 AWS 存取權的環境接手。
