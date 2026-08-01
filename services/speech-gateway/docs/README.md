# speech-gateway

台語（`nan-TW`）／客語（`hak-TW`）的 ASR/TTS 在 `packages/backend/src/asr/adapters.ts`
的 `SageMakerAdapter` 和 `packages/backend/src/tts/adapters.ts` 的
`SageMakerTtsAdapter` 裡，已經寫死要打一個 SageMaker real-time endpoint（名稱來自
`ASR_SAGEMAKER_ENDPOINT`/`TTS_SAGEMAKER_ENDPOINT` 環境變數），但這個 endpoint
目前**還沒有被部署過**——`infra/`、`infrastructure/` 都沒有用 CDK 定義它，只有
Lambda 端的 `sagemaker:InvokeEndpoint` IAM 權限。`zh-TW`/`en-US` 已經直接走
AWS Transcribe/Polly，不需要這個目錄的任何東西。

這個目錄是從獨立的 ASR/TTS PoC repo（四語言、跑過完整實測）搬過來的參考資料 +
可部署的推論程式碼骨架，用來補上那個還沒部署的 SageMaker endpoint：

- [`model-selection.md`](./model-selection.md) — 為什麼 nan/hak 選這幾個模型、
  實測 CER 數字、目前已知還沒解決的限制（尤其是**授權**：目前的候選都是
  non-commercial 授權，是否符合黑客松規則還沒確認）。
- [`sagemaker-endpoint-contract.md`](./sagemaker-endpoint-contract.md) — 直接讀
  `adapters.ts` 原始碼得到的精確 request/response 格式，加上部署步驟。
- [`MODEL_REGISTRY.json`](./MODEL_REGISTRY.json) — PoC 完整測過的所有模型清單
  （含 zh/en，僅供對照，這個 endpoint 用不到）。
- `../sagemaker/` — 照上面契約寫的 SageMaker 推論 container 骨架
  （`inference_asr.py`、`inference_tts.py`、`Dockerfile`）。**這些程式碼還沒有
  真的部署驗證過**，本機沒有 AWS 憑證，只做到語法檢查跟本地 dry-run。

PoC 原始 repo（完整實測記錄、可執行的比較介面）：見團隊內部的
`智慧長照四語 ASR/TTS PoC` 專案，這裡只搬對這個 endpoint 有直接用處的部分。
