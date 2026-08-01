# kinsun.ai Design System — MASTER

版本：v0.1
狀態：Draft｜實作用 Source of Truth，待可用性測試回饋修正
建立日期：2026-08-01
適用範圍：長者端、專業照護端（日照／居服）、家屬端的視覺、互動與 RWD 規範

> 本檔是**實作階段**的全域規範。建立任一頁面前先讀本檔；若
> `design-system/pages/<page-name>.md` 存在，該檔的規則覆寫本檔，其餘一律以本檔為準。
>
> 本檔不取代 `docs/` 的產品規格。衝突時以 `docs/` 與 `AGENTS.md` 為準，
> 並回頭修正本檔。

---

## 0. 已定案與待定案

| # | 項目 | 狀態 | 內容 |
| --- | --- | --- | --- |
| 1 | App 拓撲 | **已定案** | **單一 multi-role PWA**，程式在 `packages/frontend`，以 route 區分角色。`apps/` 的三個目錄已移除（[ADR 0006](../docs/adr/0006-frontend-stack-and-app-topology.md)）。 |
| 2 | Stack | **已定案** | **Next.js 14 App Router + TypeScript + CSS Modules + CSS custom properties**。**不是 Vite，也不用 Tailwind**——前端同時是 BFF，OAuth 交換與 access token 必須留在伺服器端（ADR 0006 §2、§3）。 |
| 3 | 主要載具 | **已採用** | **平板為主**。手機為次要，桌機僅照護端。 |

仍待 ADR、不要預先鎖定的：狀態管理函式庫、i18n 函式庫（現為 `src/lib/i18n/` 的自建
最小字典，見 §5.2）。Router 與測試框架已隨 ADR 0006 定案為 Next.js App Router 與 Vitest。

---

## 1. 設計原則（衍生自文件 04 §二，含實作意涵）

| 原則 | 實作意涵 |
| --- | --- |
| Voice First | 長者端不得要求打字。輸入法只在設定頁出現。 |
| 一次一個主要操作 | 長者端每畫面只有 1 個 filled 主按鈕，其餘一律 outline 或 text。 |
| 狀態可感知 | 每個狀態同時提供**視覺 + 文字 + 語音**。狀態資訊不得只由動畫承載。 |
| 不責怪使用者 | 失敗文案主詞是系統：「我沒聽清楚」，不是「辨識失敗」「輸入錯誤」。 |
| 確認後成為事實 | 未確認／待覆核／已發布必須有**不同的卡片形狀**，不只是不同顏色。 |
| 角色最小權限 | Permission Denied 頁在取得資料前就要能渲染，不得先畫再遮。 |
| 同一資料多種呈現 | 同一 `report_id` 在三端樣式不同，內容來源只有一份。 |
| 可復原 | 所有破壞性操作需二次確認；長者端另需「稍後再說」這類非二選一的退路。 |
| 不做醫療判斷 | 見 §2，這是最容易違反的一條。 |
| 無資料就是無資料 | `Data Insufficient` 是一等公民顯示狀態，有專屬樣式，不留白也不補字。 |

---

## 2. 最高階約束：顏色不得表達健康

文件 04 §二.9 禁止確診、疾病機率、孤獨分數與**紅黃綠燈**。這條會否決照護 dashboard
的多數標配做法。

**顏色只表達 workflow 狀態，永遠不表達長者健康狀態。**

- 綠色 `#047857` = 「這筆已覆核」，**不是**「她今天很好」。
- 琥珀 `#B45309` = 「有 3 筆待你覆核」，**不是**「需要注意」。
- 紅色 `#DC2626` = 「已撤回／破壞性操作」，**不是**「異常」。

禁止出現在任何介面的元件：健康狀態燈號、風險分數卡、情緒指數、跨長者排名或評分、
趨勢預測線、異常偵測標記。

---

## 3. Token 架構

三層：**primitive → semantic → surface**。元件只能引用 semantic 或 surface token，
不得出現 raw hex（skill §6 `color-semantic`）。

```
:root                      primitive（色階、字級、間距原始值）
:root                      semantic（--color-primary、--space-4 …）
[data-surface="voice"]     長者端覆寫
[data-surface="care"]      照護端覆寫
[data-surface="family"]    家屬端覆寫
```

Surface 由 route group 決定，掛在 `<body data-surface="...">`。

---

## 4. 色彩

### 4.1 基底

採 Healthcare App「calm cyan + health green」。**主色與 accent 在白底上僅約 3.7:1，
不能當內文色**，因此拆為 fill 用與 text 用兩組 token。

| Token | Hex | 白底對比 | 允許用途 |
| --- | --- | --- | --- |
| `--color-primary` | `#0891B2` | 3.68:1 | 填色按鈕、元件邊界、≥24px 大字 |
| `--color-primary-text` | `#0E7490` | 5.36:1 ✅ | 連結、內文級主色文字 |
| `--color-primary-weak` | `#CFFAFE` | — | 選取態底色 |
| `--color-accent` | `#059669` | 3.77:1 | 填色 CTA、圖示 |
| `--color-accent-text` | `#047857` | 5.48:1 ✅ | 「已確認」「已發布」文字 |
| `--color-foreground` | `#164E63` | 8.98:1 ✅ | 主文字 |
| `--color-muted-foreground` | `#64748B` | 4.76:1 ✅ | 次要文字（**下限**，不得再淡） |
| `--color-background` | `#ECFEFF` | — | 頁面底（長者端） |
| `--color-surface` | `#FFFFFF` | — | 卡片 |
| `--color-border` | `#A5F3FC` | — | 分隔線 |
| `--color-border-strong` | `#67E8F9` | — | 卡片外框 |
| `--color-destructive` | `#DC2626` | 4.83:1 ✅ | 撤回、刪除、拒絕 |
| `--color-ring` | `#0891B2` | — | focus ring |

Surface 覆寫：

| Token | voice | care | family |
| --- | --- | --- | --- |
| `--color-background` | `#ECFEFF` | `#F6FAFB` | `#F8FDFE` |

照護端底色刻意更中性——工作台長時間注視，飽和底色會疲勞。

### 4.2 Workflow 狀態

每個狀態**必須同時有顏色、圖示、文字**三者（skill §1 `color-not-only`）。
色弱使用者與列印稿都必須能辨識。

| 狀態 | 文字色 | 底 | 圖示 (Phosphor) | 卡片形狀 |
| --- | --- | --- | --- | --- |
| Candidate／未確認 | `#64748B` | `#F1F5F9` | `CircleDashed` | **虛線外框** |
| Needs Review／待覆核 | `#B45309` | `#FFFBEB` | `Warning` | 實線 + 左側 4px 琥珀條 |
| Confirmed／Verified | `#047857` | `#ECFDF5` | `CheckCircle` | 實線 |
| Published | `#0E7490` | `#ECFEFF` | `PaperPlaneTilt` | 實線 |
| Withdrawn／Revoked | `#DC2626` | `#FEF2F2` | `Prohibit` | 實線 + 刪除線標題 |
| Data Insufficient | `#64748B` | 45° 斜線底紋 | `Minus` | 虛線外框 |

「虛線 = 尚未成為事實」是跨三端一致的形狀語言。不得用實線卡片呈現 Candidate。

### 4.3 深色模式

v0.1 **不實作**。長者端深色模式對高齡視力（水晶體黃化、對比敏感度下降）多半是負面的，
需可用性測試驗證後再決定。Token 架構已預留，但不要在 Gate 1 花時間。

---

## 5. 字體

| 用途 | 字型 | 字重 |
| --- | --- | --- |
| 中文全部 | **Noto Sans TC** | 400 / 500 / 700 |
| 數字與英文標題 | **Figtree** | 400 / 500 / 600 / 700 |
| 表格數字 | Figtree + `font-variant-numeric: tabular-nums` | 500 |

```css
font-family: "Figtree", "Noto Sans TC", "PingFang TC",
             "Microsoft JhengHei", system-ui, sans-serif;
```

Figtree 放前面只吃 Latin 與數字，中文自動落到 Noto Sans TC。

**不使用** Noto Sans（無中文字符）、Huninn（僅 400 一個字重，做不出階層）、
任何等寬字當標題。

字型自架於自有網域，不得依賴 Google Fonts CDN（離線可用性 + 不對外洩漏使用者 IP）。
`font-display: swap`。

### 5.1 字級

| Token | voice | care | family |
| --- | --- | --- | --- |
| `--text-xs` | 18px | 12px | 14px |
| `--text-sm` | 20px | 14px | 16px |
| `--text-base` | **22px** | 16px | 18px |
| `--text-lg` | 26px | 18px | 20px |
| `--text-xl` | 32px | 20px | 24px |
| `--text-2xl` | 40px | 24px | 30px |
| `--text-3xl` | 48px | 30px | 36px |
| line-height (body) | 1.75 | 1.5 | 1.6 |

長者端 22px 是**下限不是選擇**——目標使用者 75+，skill 的 16px 是通用網頁下限，
對此族群不足。

系統字級放大到 **200%** 時三端都不得破版：不得對含文字的容器設固定高度，
不得用 `overflow: hidden` 裁切文字，長字串優先換行而非 ellipsis
（skill §6 `truncation-strategy`）。

### 5.2 介面語言（中／英切換）

| Surface | UI 語言 | 切換入口 |
| --- | --- | --- |
| voice | 中文，**不提供切換** | 無 |
| care | 中／英 | 頁首右上 |
| family | 中／英 | 頁首右上 |

長者端不放語言切換，是設計決定不是待辦：§1「一次一個主要操作」與 §6.1「長者端不得
要求精準點擊」都反對在語音畫面加這類 chrome。

**UI 顯示語言 ≠ 長者的語音互動語言。** Module A 要求的中文／臺語屬於語音互動語言，
是 domain 資料；切換 UI 語言只改瀏覽器端偏好，**不得寫入任何 domain state**，
尤其不得改動長者的語言偏好或 consent 記錄（ADR 0006 §5）。

實作為 `packages/frontend/src/lib/i18n/`：字典 + React context，**不引入 i18n 函式庫**。
新增使用者可見字串時，同時補 `zh-Hant` 與 `en` 兩個鍵；
`messages.test.ts` 會在兩邊鍵不一致時失敗。

英文字串通常較長：**任何加了英文的版面都要在 `en` 下重測 390／768 兩個寬度**，
按鈕與表頭不得因此換行破版，也不得改用 ellipsis 裁切（§5.1）。

---

## 6. 間距與觸控

4pt 基準。`--space-1: 4px` 起，`2/8`、`3/12`、`4/16`、`5/20`、`6/24`、`8/32`、
`10/40`、`12/48`、`16/64`。

Surface 密度：

| Surface | 密度 | 卡片內距 | 區塊間距 |
| --- | --- | --- | --- |
| voice | 1（極寬鬆） | 32px | 48px |
| care | 8（密集） | 16px | 24px |
| family | 4（標準） | 24px | 32px |

### 6.1 觸控目標（平板優先，高於通用標準）

| Surface | 最小 | 建議 | 間距 |
| --- | --- | --- | --- |
| voice | **64×64px** | 72×72px | ≥16px |
| care | 48×48px | 56×56px | ≥8px |
| family | 48×48px | 48×48px | ≥8px |

長者端 64px 高於 skill 的 44px 標準。理由：平板持握不穩、握力與精細動作衰退、
且多數操作不可逆（確認記憶、撤回同意）。誤觸成本高於畫面效率。

長者端**不得要求精準點擊**：無小圖示按鈕、無邊緣細條、無需拖曳的操作。

---

## 7. RWD（平板為主）

### 7.1 斷點

| 名稱 | 寬度 | 定位 | 對象 |
| --- | --- | --- | --- |
| `phone` | 390–767 | 次要 | 家屬手機、照服員應急 |
| **`tablet-p`** | **768–1023** | **主要基準** | 長者端、照護端直式 |
| **`tablet-l`** | **1024–1279** | **主要基準** | 照護端橫式、長者端橫式 |
| `desktop` | ≥1280 | 次要 | 照護端桌機、管理頁 |

**設計順序：先做 768，再向上做 1024，最後才向下做 390。** 不是 mobile-first ——
主要載具是平板，先做手機會讓平板變成「放大的手機」而浪費空間。

### 7.2 橫直式

平板會轉向，兩個方向都必須可用（skill §5 `orientation-support`）。
**不得鎖定方向。**

| Surface | 直式 768×1024 | 橫式 1024×768 |
| --- | --- | --- |
| voice | 語音按鈕置中，上下留白 | 語音按鈕維持同尺寸不放大，改左右分欄（左：按鈕／右：狀態與歷史） |
| care | 單欄 + 頂部 app bar，長者卡 2 欄 | 左側 sidebar 240px + 主區，長者卡 3 欄 |
| family | 單欄 | 單欄置中，`max-width: 720px` |

橫式高度僅 768px，扣掉瀏覽器 chrome 後可用高度約 660px。**長者端橫式時語音按鈕
不得放大**，否則會頂到底部操作區。

### 7.3 各 surface 佈局規則

**voice**
- 永遠單欄置中，`max-width: 640px`（直式）／分欄（橫式）。
- 底部操作列固定，`padding-bottom: env(safe-area-inset-bottom)`。
- 主按鈕直徑：`min(55vw, 280px)`，橫式改 `min(28vw, 240px)`。

**care**
- 長者卡格線：`repeat(auto-fill, minmax(280px, 1fr))`，自然得到 390→1 欄、
  768→2 欄、1024→3 欄、1280→4 欄。
- ≥1024 用 sidebar，<1024 用 top app bar（skill §9 `adaptive-navigation`）。
- 表格在 <768 轉為卡片列表，**不得橫向捲動**（skill §5 `horizontal-scroll`）。
- 詳情頁分頁列超出寬度時橫向捲動 tab 本身，內容不捲。

**family**
- 永遠單欄，`max-width: 720px`。閱讀導向，不需要寬版。
- 報表內容行長控制在 35–60 字元（中文約 25–35 字）。

### 7.4 硬性規則

- `<meta name="viewport" content="width=device-width, initial-scale=1">`，**不得** `user-scalable=no`。
- 高度用 `min-h-dvh`，不用 `100vh`。
- 固定的 header／bottom bar 必須為內容保留等高 padding。
- 任何斷點下 body 不得橫向捲動。
- 元件層級用 **container query**（`@container`）而非 media query——同一張長者卡在
  sidebar 內與主區內寬度不同，應各自反應。

---

## 8. 元件

### 8.1 按鈕

| 變體 | 用途 | 樣式 |
| --- | --- | --- |
| `primary` | 每畫面唯一主操作 | filled `--color-primary`，白字 |
| `accent` | 確認類（記住、覆核通過） | filled `--color-accent`，白字 |
| `secondary` | 次要 | outline 2px |
| `ghost` | 第三層 | 純文字 + 底線 |
| `destructive` | 撤回、刪除 | outline `--color-destructive`，**與主操作至少間隔 24px** |

- 每畫面**只有一個** filled 按鈕（skill §4 `primary-action`）。
- 非同步操作中按鈕 disable 並顯示 spinner（skill §2 `loading-buttons`）。
- Disabled：`opacity: 0.45` + `cursor: not-allowed` + `aria-disabled`。
- 長者端按鈕一律**圖示 + 文字**，不得只有圖示。

### 8.2 焦點

```css
:focus-visible {
  outline: 3px solid var(--color-ring);
  outline-offset: 2px;
  border-radius: 4px;
}
```
長者端加粗到 4px。**任何情況下不得移除 focus ring**（skill §1）。

### 8.3 圓角與陰影

| Token | 值 |
| --- | --- |
| `--radius-sm` | 8px |
| `--radius-md` | 12px |
| `--radius-lg` | 16px（長者端卡片） |
| `--radius-full` | 9999px |

陰影只有三階：`--shadow-1`（卡片）、`--shadow-2`（浮層）、`--shadow-3`（modal）。
不得出現第四種陰影值（skill §4 `elevation-consistent`）。

### 8.4 圖示

**Phosphor Icons**（`@phosphor-icons/react`），統一 `weight="bold"`；
長者端用 `weight="fill"` 增加實心面積。

| Surface | 圖示尺寸 |
| --- | --- |
| voice | 32 / 40 / 48px |
| care | 16 / 20 / 24px |
| family | 20 / 24px |

**禁止 emoji 當結構圖示。** 純圖示按鈕必須有 `aria-label`。

---

## 9. 動效

`--motion: 2/10（Subtle）`。全域 150–300ms，進場 `ease-out`，退場為進場的 60–70%。

**長者端只允許一個動態元素**：語音按鈕的呼吸／音量環。這是唯一具語意的動畫
（表達「我在聽」）。

- 只動 `transform` 與 `opacity`。
- `prefers-reduced-motion: reduce` 時退化為靜態環，**狀態仍由文字與語音完整表達**。
- 照護端與家屬端**不使用** scroll reveal。資料必須一進場即可讀。

---

## 10. 狀態規格（文件 04 §七）

每個核心頁面都必須實作其對應狀態，這不是選配。

### 10.1 長者語音首頁 — 9 狀態

| 狀態 | 視覺 | 文案 |
| --- | --- | --- |
| Idle | 靜態環，primary | 按一下開始說話 |
| Recording | 呼吸環 + 音量反饋，accent | 我在聽… |
| Processing ASR | 環轉為進度感，primary | 我正在聽清楚你的話 |
| Generating | 同上 | 我正在整理回答 |
| Playing | 播放波形，accent | 顯示回覆內容 + 重新播放 |
| Low Confidence | 環暫停，全屏確認卡 | 我聽到「…」，是這樣嗎？ |
| Timeout | 環轉灰 | 剛剛沒有聽到聲音，要再試一次嗎？ |
| Offline | 環轉灰 + `WifiSlash` | 網路好像斷了，等一下再試 |
| Permission Denied | 環轉灰 + `MicrophoneSlash` | 要先讓我使用麥克風才能說話（附白話步驟） |

失敗文案主詞一律是系統。不得出現「錯誤」「失敗」「無效」。

### 10.2 照護端 — 7 狀態

Loading（skeleton，**不得顯示過期資料假裝完成**）／Empty／Needs Review（顯示數量與原因）／
Updated（顯示最後更新、修正者、版本）／Permission Denied（**不顯示長者姓名或任何敏感內容**）／
Assignment Expired（提供返回行程入口）／Data Insufficient（不產生陪伴結論）。

### 10.3 家屬端 — 8 狀態

No Report／Draft·Needs Review（**家屬不可見，前端不得渲染**）／Published／
Withdrawn（不保留舊敏感內容）／Notification Failed（App 仍顯示報表）／
Authorization Expired／Consent Revoked／Data Insufficient。

---

## 11. 家屬端資料紅線

前端**不得渲染**以下欄位，即使 API 回傳了：逐字稿、ASR 信心值、未覆核事件、
內部照護筆記、診斷式分數、完整 Prompt（AGENTS.md §8.1、文件 04 §8.7）。

這道 runtime assert **已實作**於 `packages/frontend/src/lib/api/family-guard.ts`，
在 `listFamilyReports` 內對 **raw Core payload** 執行（必須在 `toFamilyReportView`
之前——mapping 只留已知欄位，洩漏的逐字稿會被靜默丟掉，違約就永遠看不到）。

兩種違規的處置刻意不同：

| 違規 | 處置 | 理由 |
| --- | --- | --- |
| 出現本節列的受限欄位 | **丟 `FamilyDataRedlineError`**，整頁失敗 | 契約已破到無法界定範圍，繼續渲染等於猜測還有什麼是壞的 |
| 回傳非 `PUBLISHED`／`WITHDRAWN` 的報表 | **丟棄該筆**，其餘照常顯示，並記錄違規 | 沒進 DOM 就沒洩漏；為一筆壞資料讓家屬看不到其他合法報表是錯的代價 |

被丟棄的報表**不得**在畫面上留下任何痕跡——讓家屬知道有一份草稿存在，本身就是揭露（§10.3）。

新增家屬端 endpoint 時要一併接上這兩道；受限欄位清單也在該檔，以正規化（小寫、去
`_`／`-`）比對，casing 或 camelCase 變動不會讓它變成空轉。

---

## 12. 資料視覺化

**Gate 1 不引入圖表函式庫。**

文件 04 §十.7 禁止醫療趨勢預測，因此折線趨勢圖與異常偵測圖不可使用。

| 需求 | 做法 | 禁止 |
| --- | --- | --- |
| 事件時間軸 | 垂直時間軸列表 + 來源連結 | 折線圖 |
| 本週互動次數 | 數字 + 7 格 bar（**互動次數**，非健康分數） | 趨勢線、預測 |
| 待覆核數量 | 數字 badge | 圓餅圖 |

Wave 3 若確有需求再評估 Recharts，並須先確認不構成健康評估。

---

## 13. 無障礙驗收（每頁必過）

- [ ] 內文對比 ≥4.5:1，大字與 UI 元件 ≥3:1
- [ ] focus ring 可見且未被移除，Tab 順序符合視覺順序
- [ ] 純圖示按鈕有 `aria-label`
- [ ] 標題階層 h1→h6 不跳級
- [ ] 錯誤用 `role="alert"` 或 `aria-live` 播報
- [ ] 資訊不單靠顏色傳達（顏色 + 圖示 + 文字）
- [ ] 系統字級 200% 不破版
- [ ] `prefers-reduced-motion` 下動畫停用且不損失資訊
- [ ] 觸控目標達 §6.1 標準
- [ ] 390 / 768 / 1024 / 1280 四個寬度 + 平板橫直式皆無橫向捲動

---

## 14. 明確禁止

- emoji 當結構圖示
- 健康狀態燈號、風險分數、情緒指數、跨長者排名
- 趨勢預測、異常偵測視覺
- AI 紫粉漸層（本產品不是 AI 工具，會折損可信度）
- 霓虹色、重動效
- 深色模式（v0.1）
- 元件內 raw hex
- 移除 focus ring
- `user-scalable=no`
- 長者端純圖示按鈕
- 家屬端渲染 §11 的任何欄位
- Demo／測試／截圖使用非合成資料（AGENTS.md §4）

---

## 15. 相關檔案

- 全頁面 HTML Demo：`docs/demo/ui/index.html`
- 頁面覆寫：`design-system/pages/<page-name>.md`（目前無）
- 頁面清單與優先級：`docs/04…資訊架構、UX 與 User Flow v0.1.md` §五
- 不可違反邊界：`AGENTS.md` §4
