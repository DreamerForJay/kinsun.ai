# 成員 D 責任範圍：Speech

成員 D 負責 Gate 1 的 Speech 邊界：台語／客語 ASR、低信心確認、TTS 候選評估、
SageMaker BYOC 與可重複的 Synthetic 測試工作台。

正式跨服務邊界固定為：

```text
Speech ASR → 人工確認 → Core API → Agent Runtime／RAG → Core 安全回覆 → Speech TTS
```

成員 D 不繞過 Core 的 Authorization／Consent Gate，不把外部 TTS Space 當正式 provider，
也不宣稱尚未部署的 TTS Endpoint、Voice transport 或母語品質驗證已完成。

完整交接見 [`docs/handover/2026-08-02-member-d-speech-integration.md`](../handover/2026-08-02-member-d-speech-integration.md)。
