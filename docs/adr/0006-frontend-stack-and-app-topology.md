# ADR 0006：前端技術選型與 App 拓撲收斂

- 狀態：Accepted
- 日期：2026-08-02
- 相關文件：04｜資訊架構、UX 與 User Flow v0.1、12｜實作計畫與交付路線 v0.1 §目錄骨架
- 相關：[ADR 0003](0003-core-api-framework-and-schema-authority.md)、`design-system/MASTER.md` §0
- 解除 AGENTS.md §11 的「Frontend Framework 與 PWA 技術」待決項

## 背景

`design-system/MASTER.md` §0 列了兩項待決，兩項的敘述都與 repository 的實際內容不符。
在寫任何新頁面之前必須先對齊，否則設計規範與程式碼會各自長大。

盤點結果（排除 `node_modules`、`.next`、`cdk.out`、`.venv`）：

| 目錄                | 內容                                 | 行數  | 狀態                          |
| ------------------- | ------------------------------------ | ----- | ----------------------------- |
| `packages/frontend` | Next.js 14 App Router + TypeScript   | 5,747 | 可執行，有測試，已接 core-api |
| `apps/elder-web`    | Next.js 14，自帶 `package-lock.json` | 407   | 孤兒，不在任何 workspace 內   |
| `apps/care-web`     | 只有 `.gitkeep`                      | 0     | 空                            |
| `apps/family-web`   | 只有 `.gitkeep`                      | 0     | 空                            |
| `docs/demo/ui`      | 靜態 HTML demo                       | 2,254 | 設計參考，非應用程式          |

### MASTER.md §0 #1「App 拓撲待確認」

實際上已經有答案。`packages/frontend` 就是單一 multi-role PWA：同一個 Next.js 應用
以 route 區分角色（`/` voice、`/dashboard` care、`/family` family、`/staff` 登入），
與 AGENTS.md §6 Target Architecture 的「Single multi-role PWA」一致。

`apps/` 底下三個目錄源自文件 12 的骨架，其中兩個是空的，第三個是重複品。

### MASTER.md §0 #2「已採用 Vite + React + Tailwind」

與現況不符，而且**不應該照著它做**。實際是 Next.js 14 App Router + CSS Modules +
CSS custom properties，沒有 Tailwind。

關鍵在於 `packages/frontend` 不只是 SPA，它同時是 BFF：

- `src/app/backend/auth/{login,callback,logout,session}/route.ts` 在**伺服器端**完成
  Cognito OAuth code exchange。
- `src/lib/server/auth-cookie.ts` 把 access token 存成 httpOnly cookie，**token 不進瀏覽器**。
- `src/app/backend/core/[...path]/route.ts` 反向代理到 `CORE_API_INTERNAL_URL`
  （預設 `http://127.0.0.1:8000`），以 header allowlist 轉發，並在此檢查 CSRF origin
  與 body 上限。

改成 Vite SPA 會拆掉這一層：OAuth 交換必須移到瀏覽器，access token 必須存在
JavaScript 可讀的地方。這不是偏好問題，是把一個目前擋得住 XSS 竊取 token 的設計
改成擋不住。文件 07 的 Threat Model 不接受這個交換。

## 決策

### 1. 單一 multi-role PWA，位置是 `packages/frontend`

移除 `apps/elder-web`、`apps/care-web`、`apps/family-web`。
`apps/README.md` 保留一行說明指向本 ADR，避免有人照文件 12 的骨架把它們重建回來。

角色以 route group 區分，不以獨立部署單元區分。理由：

- 三端共用同一組 domain 型別、API client 與 token 系統。拆成三個 app 會複製三份，
  而 `src/lib/api/` 的授權相關程式碼複製後就會分歧——`family` 端的資料紅線
  （MASTER.md §11）尤其不能有第二份實作。
- BFF 的 auth 路由只需要一份。三個 app 就是三組 OAuth callback URL 與三份 cookie 設定。
- Demo 是單一使用者旅程跨三個角色，同一個 origin 切換最省事。

`apps/elder-web` 不做遷移：它的 `ElderVoiceInterface.tsx` 是 `setTimeout` 模擬的假對話，
沒有接任何 API，且自帶一套不吃 token 的 CSS。`packages/frontend` 的
`src/components/voice/` 已經涵蓋且實際接了 API。直接刪除，不保留分支。

### 2. Framework：Next.js 14 App Router + TypeScript

**MASTER.md §0 #2 的「Vite + React」作廢**，理由見背景。本 ADR 生效後同步修正該表。

- App Router（不是 Pages Router）。已在用，且 route handler 是 BFF 的基礎。
- React 18 + TypeScript strict（繼承 `tsconfig.base.json`）。
- Server Component 為預設，需要狀態的頁面才標 `'use client'`。

### 3. 樣式：CSS Modules + CSS custom properties，不引入 Tailwind

`src/app/tokens.css` 已依 MASTER.md §3 實作 primitive → semantic → surface 三層，
`[data-surface]` 覆寫也已到位。Tailwind 現在加進來會產生第二套樣式系統：
utility class 與 CSS 變數各自表述同一組 token，而 MASTER.md §14 禁止元件內 raw hex
這條在 utility class 底下很難用工具檢查。

代價要說清楚：CSS Modules 沒有 Tailwind 的一致性壓力，容易寫出 inline style 硬編色碼。
**目前程式碼已經有這個問題**——`dashboard/`、`family/` 底下多處 inline style 用
`#718096`、`#e53e3e`、`#2b6cb0`，違反 MASTER.md §14。這筆技術債記在「後果」，
需要一個 lint 規則守住，不是靠自律。

### 4. Package manager：npm workspaces（僅前端／TypeScript 側）

`package.json` 已宣告 `workspaces: ["packages/*", "infrastructure"]`，
根目錄有 `package-lock.json`，無 `pnpm-lock.yaml`。因此 npm 是既成事實。

Python 側維持 uv（[ADR 0001](0001-package-manager-uv.md)），兩者不共用，各自 lock。

一個待清理的不一致：`node_modules/` 底下存在 pnpm 形式的 store（`.pnpm/`），
但沒有對應的 `pnpm-lock.yaml`。應視為誤用 pnpm 留下的殘留物並清掉，
以免哪天有人依它推論 package manager 是 pnpm。

### 5. i18n：自建最小字典，不引入 i18n 函式庫

MASTER.md §0 要求不要預先鎖定 i18n 函式庫。同時 AGENTS.md §3 把 English 排在 Wave 3。
本次只做**照護端與家屬端**的中英切換，實作為 `src/lib/i18n/` 底下的字典與 React
context，約 200 行，不引入 next-intl／i18next。

長者端維持中文。理由不是省事：MASTER.md §1「一次一個主要操作」與 §6.1「長者端不得
要求精準點擊」都反對在語音畫面加語言 chrome，而 Module A 要求的臺語支援屬於
**語音互動語言**，與 UI 顯示語言是兩件事，不應共用一個開關。

**UI 語言不得寫入 domain state。** 切換語言只改 cookie 與 React state，
不呼叫任何 Core API，尤其不得改動長者的 `language_preference` 或 consent 記錄。
Cookie 名為 `kinsun_ui_locale`，非 httpOnly（它是 UI 偏好，不是憑證），
且因為 `core-proxy.ts` 用 header allowlist 轉發、完全不轉發 cookie，
這個值不會抵達 Core API。

未來若需要 Server Component 翻譯、複數規則或日期在地化，再開 ADR 換 next-intl；
屆時只需替換 provider，字典鍵不變。

## 後果

- AGENTS.md §11 的「Frontend Framework 與 PWA 技術」待決項解除。
  §11 其餘項目（IaC、Region、Bedrock model、Retention 政策等）不受本 ADR 影響。
- MASTER.md §0 三列全部從「待確認」轉為「已定案」，並修正 #2 的技術內容。
- `apps/` 目錄清空，文件 12 的三-app 骨架被本 ADR 取代。若日後確有拆分需求，
  需新 ADR 推翻本決定，不得直接把目錄加回來。
- **未償技術債（明確記錄，不假裝不存在）**：
  - `dashboard/`、`family/` 的 inline style raw hex 違反 MASTER.md §14，尚未修。
  - `care`／`family` route 先前沒有設定 `data-surface`，等於一直吃 `:root` 預設字級。
    本次隨 i18n 的 layout 一併補上，但既有頁面的間距／字級仍未依 §6 的密度表調整。
  - MASTER.md §5 要求自架字型，`globals.css` 已註明 `@font-face` 尚未建立，
    目前落回系統字型。
  - 前端無 lint 規則守 raw hex，也沒有 §13 無障礙驗收的自動化檢查。

## 這次刻意不決定的事

`packages/backend`（8,093 行 TypeScript，AWS Lambda + DynamoDB + Bedrock SDK）與
`infrastructure/`（AWS CDK，991 行）構成**第二套後端與一個未經 ADR 的 IaC 選型**，
與 `services/core-api`（25,646 行 Python／FastAPI／Aurora）平行存在。

兩者牴觸現行規範：

- DynamoDB 作為儲存牴觸 AGENTS.md §6「Aurora PostgreSQL／Domain Core 是正式交易資料
  與狀態的 Source of Truth」。
- CDK 牴觸 AGENTS.md §11「IaC 工具」仍待決。

目前 `packages/frontend` 的 BFF 只代理到 Python core-api，沒有任何路徑打
`packages/backend`。因此本 ADR 不受其影響，也不代為決定其去留。

這需要獨立的 ADR 0007，且需要先確認那 8,093 行是否仍有人維護。
在該 ADR 出來之前，**不要基於 `packages/backend` 的存在推論任何架構事實**，
也不要為了「保持一致」把新程式寫進去。
