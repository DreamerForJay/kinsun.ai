# 公開 Gradio TTS 候選評估

本流程只用來比較候選模型，不是正式 Speech Gateway。公開 Space 的可用性、
延遲、資料保存方式及底層授權都不受本專案控制，因此不得傳送真實長者內容。

## 已確認的 API

| 語言 | Space | API | 備註 |
| --- | --- | --- | --- |
| 客語 | `ivanusto/tw-hakka-tts` | `/predict` | 支援四縣、海陸、大埔、饒平、詔安、南四縣 |
| 台語 | `tbdavid2019/Taiwanese-tts` | `/handle_tts` | 會轉送外部 API，Space 說明指出保存最近 50 筆紀錄 |

客語 Space 的程式碼標示 MIT，但底層模型卡目前列為非商用授權候選；正式部署前
仍需 Owner／法務確認。台語 Space 沒有清楚授權聲明，而且會把輸入交給外部服務，
只能使用 Synthetic 測試文字。

## 安裝

```powershell
.\evals\speech\.venv\Scripts\python.exe -m pip install `
  -r .\evals\speech\requirements-external-tts.txt
```

## 執行 Synthetic 測試

客語四縣：

```powershell
.\evals\speech\.venv\Scripts\python.exe .\evals\speech\evaluate_external_tts.py `
  --provider hak --hakka-dialect sixian --synthetic-only
```

台語：

```powershell
.\evals\speech\.venv\Scripts\python.exe .\evals\speech\evaluate_external_tts.py `
  --provider nan --taiwanese-model model6 --synthetic-only
```

輸出位於 `evals/reports/tts/<provider>/`：

- `output.wav`：人工聽測用音訊。
- `result.json`：模型、腔調、羅馬字／IPA（若供應者有回傳）與延遲。

`result.json` 刻意不保存輸入原文。人工聽測應記錄可理解度、自然度、腔調正確性、
語速與危險誤讀；未經母語者覆核，不得宣稱模型已符合客語或台語品質門檻。

## 不可使用的資料

- 真實長者姓名、聲音、逐字稿或健康資訊。
- 未取得明確再利用授權的客委會語料。
- 客製化語者錄音；這會把聲紋／生物識別資料傳至第三方，亦違反競賽資料限制。

正式版本應部署獨立的 `kinsun-speech-tts-v1` SageMaker Endpoint，並以固定模型
revision、無公開存取、無資料擷取及可回退版本取代上述外部 Space。
