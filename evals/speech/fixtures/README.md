# Synthetic Mock 音訊

`synthetic_mock_tone.wav` 由 `generate_synthetic_wav.py` 產生，是 1.5 秒的雙提示音，完全不含
真人語音、個人資料、健康資料或生物識別資訊。旁邊的 `.txt` 是團隊自寫的 Synthetic 台語
逐字稿，供 `MockASRAdapter` 回傳固定結果。

這組 fixture 只能測試錄音檔載入、播放、Mock adapter、JSON 載出及評測介面，不能用來宣稱
任何模型的 ASR 準確率。需要重新產生 WAV 時執行：

```powershell
.\evals\speech\.venv\Scripts\python.exe .\evals\speech\generate_synthetic_wav.py
```
