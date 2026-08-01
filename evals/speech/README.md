# Speech evaluation

本目錄只使用團隊自寫的 Synthetic 或已核准去識別資料，評估 ASR 的逐字準確度、關鍵詞、
否定詞、人工語意判定與延遲。不得放入真實長者錄音、逐字稿、個資、健康資料或聲紋資料。

## 已提供工具

- `evaluate_transcript.py`：標準函式庫即可執行的 CER 與詞彙召回率計算。
- `notebooks/speech_evaluation.ipynb`：圖表、逐字差異與可下載報告。
- `run_local_asr.py`：下一階段的單一命令列入口，執行真實 Taiwan-Tongues ASR。
- `generate_synthetic_wav.py`：產生不含真人聲音的 Mock 提示音。
- `speech_workbench.py`：本機 Gradio 工作台，支援台語／客語 ASR、低信心確認、
  Core → Agent/RAG 與 TTS 測試；固定綁定 `127.0.0.1` 且不建立公開分享網址。
- `asr_benchmark_summary.json`：既有本機公開語料 benchmark 的彙總數字，不包含音訊、
  逐字稿、個資或聲紋；與 Synthetic case-level CER 分開呈現。

Notebook 負責完整評估視覺化，Gradio 負責人工操作流程，命令列工具負責可重現推論。

## 安裝 Notebook 環境

```powershell
.\scripts\setup_speech_eval.ps1
```

環境只建立在 `evals/speech/.venv`，不會修改 core-api 或 agent-runtime 的虛擬環境。

## 開啟 Notebook

```powershell
.\evals\speech\.venv\Scripts\python.exe -m jupyterlab `
  .\evals\speech\notebooks\speech_evaluation.ipynb
```

開啟後選 `Run` → `Run All Cells`。Notebook 會輸出 CER 表格、圖表、文字差異與 JSON／CSV／
HTML 報告。`DISPLAY_CER_GUIDE` 只控制圖上的參考線，不是正式驗收門檻。

## 執行既有 Synthetic 評測

```powershell
.\evals\speech\.venv\Scripts\python.exe .\evals\speech\evaluate_transcript.py `
  --input .\evals\speech\synthetic_cases.jsonl `
  --output .\evals\reports\speech-synthetic-results.json
```

## 執行真實本機 ASR

模型環境與執行方式請看 `services/speech-gateway/docs/local-asr-evaluation-guide.md`。執行工具
要求明確傳入 `--synthetic`，避免誤把真實人物錄音送入評測流程。

## 指標解讀

| 指標 | 作用 | 限制 |
| --- | --- | --- |
| `raw_hanji_cer` | 原始字元錯誤率 | 會懲罰標點與書寫慣例差異 |
| `normalized_hanji_cer` | 移除 Unicode／空白／標點差異後的 CER | 華語意譯仍會與台語逐字稿不同 |
| `tailo_cer` | 台羅輸出與參考的 CER | 模型有輸出台羅時才能計算 |
| `keyword_recall` | 必須保留的逐字關鍵詞 | 關鍵詞清單需要人工建立 |
| `negation_recall` | 「未、莫、不要」等否定語意是否保留 | 不代表整句語意一定正確 |
| `semantic_intent_correct` | 人工判斷意思是否保留 | 不由 deterministic evaluator 自動推論 |

Raw 模型輸出不得被正規化結果覆寫。華語意譯可能語意接近，但仍不是正確的台語逐字稿；
因此 CER 與人工語意判定必須分開呈現。

## 語言覆蓋與目前品質證據

`kinsun-speech-asr-v1` 只開放 `nan-TW` 與 `hak-TW`。底層 Taiwan-Tongues
v2.0 還支援 `zh`、`en`、`id`，但目標架構的華語／英語走 AWS Transcribe。

| 評估來源 | 語言 | Micro CER | Micro WER | 解讀 |
| --- | --- | ---: | ---: | --- |
| 既有本機公開語料 benchmark | 台語 `nan` | 76.9% | 83.3% | 品質差，必須人工確認 |
| 既有本機公開語料 benchmark | 客語 `hak` | 32.3% | 91.7% | 詞錯誤仍高，不可宣稱通過 |
| 團隊 Synthetic case | 台語 `nan-TW` | 83.3%（正規化） | N/A | 只有一例，不能當整體準確率 |

目前沒有可誠實加入的客語 Synthetic case-level 輸出；不可為了表格完整而虛構結果。

## 測試資料與參數

每筆 JSONL 必須包含 Synthetic／去識別來源聲明、語言、參考逐字稿、模型原始輸出、模型
ID、不可變 revision、decoder 設定與實測延遲。`required_keywords` 與
`required_negations` 只能加入參考逐字稿真的包含的詞。

Provider confidence 只可存在受控評測資料，不得進 API 回應、一般 Log、Domain Event、家屬
報告或截圖。

## 測試

```powershell
.\evals\speech\.venv\Scripts\python.exe -m unittest discover `
  -s .\evals\speech\tests -v
```
