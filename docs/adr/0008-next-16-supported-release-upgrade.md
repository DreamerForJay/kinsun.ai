# ADR 0008：Next.js 16 supported-release upgrade

- 狀態：Accepted
- 日期：2026-08-02
- 相關：[ADR 0006](0006-frontend-stack-and-app-topology.md)、
  [ADR 0007](0007-canonical-backend-and-aws-deployment-authority.md)

## 背景

`packages/frontend` 同時是 multi-role PWA 與 Cognito/Core API BFF。原本的
`next@14.2.35` 已不在 upstream 支援線，且 production dependency audit 有 high severity
結果，因此 ADR 0006 禁止把該版本暴露為公開 OAuth 入口。

升級時還發現舊 lockfile 讓 hoisted Next.js 解析到 React 18、app 解析到 React 19；這會讓
standalone image 帶入錯誤 major。依賴樹必須只有一份 React，不能只以本機 build 成功判定。

## 決策

1. Frontend 固定使用 `next@16.2.12`、`react@19.2.8`、`react-dom@19.2.8`，不用 caret。
   根 workspace 同版固定 React 與型別，確保 npm hoisting、測試與 standalone tracing 只解析
   一個 React major。Node.js 最低版本同步提高為 `20.9.0`。
2. 採用 Next.js 16 預設 Turbopack，不保留 `--webpack` fallback。`cookies()`、page params、
   `searchParams` 與 route-handler params 全部改成 async contract；
   `outputFileTracingRoot` 使用穩定的 top-level config。
3. `next-env.d.ts` 視為生成檔並忽略。Type gate 固定先跑 `next typegen`，再跑
   `tsc --noEmit`，讓乾淨 checkout 也能產生 typed routes。
4. 截至決策日，Next.js 最新正式版仍直接固定 vulnerable `postcss@8.4.31`，並以
   `^0.34.5` 引入 vulnerable Sharp。根 `overrides` 只限 `next@16.2.12`，固定為
   `postcss@8.5.18` 與 `sharp@0.35.3`；兩者也在根 workspace 明確固定，避免 npm 保留舊的
   nested package。每次升 Next 都必須重新檢查並移除已不需要的 override。
5. Sharp 0.35 超出 Next 宣告的 0.34 range，因此除了 unit/build gate，必須以 Linux/amd64
   standalone container 實際測試 `/_next/image`。只看 Windows build 不足以通過。

## 驗證與 gate 結果

- 乾淨 `npm ci`：通過。
- `next typegen && tsc --noEmit`：通過。
- Frontend unit tests：80/80 通過。
- Next.js 16.2.12 Turbopack production build：通過。
- Frontend production dependency audit：0 vulnerabilities。
- Linux/amd64、non-root standalone image：build 通過；runtime 只解析 React 19.2.8 與
  Sharp 0.35.3；`/health`、`/sign-in`、`/_next/image` 均回 200。

原本由 Next.js 14 production dependencies 造成的公開部署 blocker 已解除。這不等於 AWS
application rollout 已完成：ECR push/digest scan、Cognito callback、migration、consent bootstrap、
內部 smoke 與 scale-to-1 仍依 ADR 0007 各自 fail closed。

完整 audit 仍會回報 Vitest 1 開發工具鏈的 dev-server advisories；Vitest 不進 standalone
runner，測試只使用非監聽的 `vitest run`。這是獨立的開發工具升級工作，不得把它描述成
Frontend production runtime 漏洞已復發。

## Rollback

若 staging runtime 發生 Next 16/React 19 相容性問題，停止 rollout 並回退 application image
digest；不得把已停止支援的 Next.js 14 image 重新公開。修正後需重跑本 ADR 全部 gate，尤其
clean install、production audit 與 Linux `/_next/image` smoke。
