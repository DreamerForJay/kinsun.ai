# nan-TW / hak-TW 模型選型（來自 PoC 實測）

`zh-TW`/`en-US` 已經走 AWS Transcribe/Polly，本文件只談 SageMaker endpoint 要背後
跑哪個模型，也就是 `nan`（台語）跟 `hak`（客語）。完整比較過程、更多候選、CER
計算方式見 PoC repo 的 `local_poc/docs/test_log.md` 與 `MODEL_REGISTRY.json`（本目錄
也有一份副本）。

## ⚠️ 授權：目前所有 nan/hak 候選都是非商用授權

在真的把任何一個模型包進正式部署的 SageMaker endpoint 前，這件事需要先跟主辦方/
法務確認，不是技術問題：

| 模型 | 授權 |
|---|---|
| `adi-gov-tw/Taiwan-Tongues-ASR-CE-v2.0`（已部署 ASR） | TRAIL 類條款，需個別審閱，**不可標示為 MIT** |
| `facebook/mms-tts-nan` / `facebook/mms-tts-hak` | CC-BY-NC-4.0（非商用） |
| `formospeech/yourtts-htia-240704`（VoxHakka） | CC-BY-NC-4.0（非商用） |

呼應 `AGENTS.md` 已知問題 #1：黑客松規則是否要求「僅限 AWS 服務提供之基礎模型」還沒
確認。如果答案是「是」，這整條 SageMaker 自架路線都可能不能進正式提交，只能當內部
可行性佐證。**這個沒確認之前，不要假設下面這些模型可以直接部署成正式服務。**

## ASR：nan / hak 都用同一個模型

**`adi-gov-tw/Taiwan-Tongues-ASR-CE-v2.0`**（SageMaker CTranslate2／faster-whisper 版本，
不是 CT2 版）：

| 語言 | Micro CER | Micro WER |
|---|---:|---:|
| nan | 76.9% | 83.3% |
| hak | 32.3% | 91.7% |

比較過的其他候選都沒贏：
- **Breeze-ASR-26**（`MediaTek-Research/Breeze-ASR-26`，Apache-2.0）：兩種呼叫方式都測過，
  `chunk_length_s=0` 生成失控（CER 466%、平均延遲 59s、最慢 220s）；社群 CT2 轉檔版本
  CER 72.5%（略贏），但平均延遲 13s、有 297s 離群值，不穩定，未採用。
- **NUTN-KWS/Whisper-Taiwanese-model-v0.5**（CC-BY-NC-4.0）：nan CER 90.4%，更差。

**已知限制**：
- Taiwan-Tongues 官方發行包沒有 nan/hak 專屬 decoder token，實際上是透過共用的
  `<|zh|>` token 解碼（見 `generation_config.json`）——這是打包問題，不代表模型能力上限，
  但目前沒有更好的替代方案。
- 部分 CER 是「用字慣例不同」而非「聽錯」：台語語意正確但被轉寫成對應華語漢字（例如
  「毋免驚」被寫成「不用怕」），沒有像 zh 簡繁那樣的 OpenCC 工具可以校正，是已知的
  CER 數字失真來源，沒有簡單修法。
- 76.9%／32.3% CER 離「可用」都還有明顯差距，不是這次整合能解決的問題——這個
  endpoint 上線後，nan 的辨識品質預期仍然很差，這件事需要讓使用這個 endpoint 的
  上層（LLM 對話流程、guardrail）知道，不要假設 ASR 輸出可靠。

## TTS：nan 目前沒有真的能用的方案，hak 有

### nan：`facebook/mms-tts-nan` —— **已修復（2026-08-02，taibun 漢字→台羅前處理）**

這是目前找到唯一的台語 TTS 模型，tokenizer 只認羅馬字輸入。系統統一輸出繁體中文
漢字，直接餵漢字會產生 0 個 token、模型內部相對位置編碼算出負數長度而崩潰
（`RuntimeError: narrow(): length must be non-negative`），所以歷史上 nan TTS
一直只會文字降級、不會出聲音。

**修復方式**：`MmsTTSAdapter` 在 nan 合成前先經過
`speech_normalization.to_tailo()`，用 [taibun](https://github.com/andreihar/taibun)
（MIT、純 Python、離線）把漢字轉台羅。2026-08-02 以 PoC `.venv310` 實測 4 句
（含「逐家好」「毋免驚，我陪你」），台羅/POJ、帶調/去調共 16 個變體全部成功
合成音訊；tokenizer 詞彙表含台羅聲調符號（組合用 U+0304/U+030D 及預組合母音）
但**沒有 POJ 的鼻音符 ⁿ (U+207F)**，因此選定「台羅、保留聲調」為轉換目標。

先前死路的原因也已查明：`tai5-uan5-gian5-gi2-kang1-ku7` 是框架不是轉換器——
其 `辭典` 模組全是空容器類別，**不內建任何漢字→台羅辭典資料**，官方範例回空
（音欄位 `'--'`）是設計如此，不是缺資料包的 bug；連帶的 `kesi` 套件同樣沒有
辭典。意傳線上 API（hokbu.ithuan.tw）實測回 500/404，不可依賴。

**殘餘限制**：taibun 轉換品質與 mms-tts-nan 的音質**尚無母語者評分**；taibun
是閩南語專用，**不可**套用到 hak。

### hak：`formospeech/yourtts-htia-240704`（VoxHakka，推薦）

YourTTS 架構，6 個腔調（sixian/hailu/dapu/raoping/zhaoan/nansixian），內部用
`formog2p` 先把漢字轉成 IPA 再合成，**不會撞到 mms 那個漢字崩潰問題**。已驗證
sixian（四縣）、hailu（海陸）兩個腔調端到端可以出聲音。

**已知限制**：目前系統要用哪個腔調當正牌（四縣還是海陸）還沒有明確決定，錄音／
逐字稿／模板／TTS／預錄音檔庫全部要用同一腔調，混腔會讓資料失真——這件事需要
團隊先決定，不是技術問題。

備援：`facebook/mms-tts-hak` 存在，但有跟 mms-tts-nan 一樣的漢字 tokenizer 限制，
實務上也需要羅馬字輸入才會出聲音，優先度低於 VoxHakka。

## 目前完全沒有母語者評分

上面所有結論都只驗證了「技術上能不能動、CER 數字」，**沒有任何母語者對自然度/
腔調正確性做過評分**。正式部署前這一步還是要做。
