# 本機 Taiwan-Tongues ASR 評測

此流程取代 Gradio，以一個命令完成音訊正規化、真實 ASR 與選用的 CER 評測。只允許
Synthetic／已核准去識別音訊，不使用真實長者資料。

## 建立獨立模型環境

模型依賴較大，不安裝到 Notebook、core-api 或 agent-runtime 的環境：

```powershell
uv venv .\services\speech-gateway\.venv-asr --python 3.10
uv pip install --python .\services\speech-gateway\.venv-asr\Scripts\python.exe `
  --requirements .\services\speech-gateway\sagemaker\requirements-asr.txt
```

`torch` 的 CPU／CUDA build 尚未依正式 SageMaker instance 定案；本機指令會安裝套件索引
提供的預設版本，只作 baseline，不代表部署版本已核准。

## 執行

```powershell
.\services\speech-gateway\.venv-asr\Scripts\python.exe `
  .\evals\speech\run_local_asr.py `
  --audio .\path\to\synthetic-audio.mp3 `
  --language nan-TW `
  --reference "我猶未講煞，你先莫插話好無？" `
  --keywords "講煞,插話" `
  --negations "未,莫" `
  --output .\evals\reports\local-asr-result.json `
  --synthetic
```

第一次執行會從模型來源下載權重，所需時間與磁碟空間取決於網路及 cache。輸出 JSON 會
記錄模型 ID、版本、延遲、real-time factor、逐字稿與 CER；不得上傳真實人物資料。
