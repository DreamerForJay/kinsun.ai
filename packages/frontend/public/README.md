# public/ 資產說明

## PWA icon 現況

目前 PWA icon 直接指向 `mascot.png`，`manifest.json` 中的 `sizes` 為實際檔案尺寸
（2048×2048）。

正式版應另外產生 192×192 與 512×512 的 maskable icon，放在 `/icons/` 底下，並更新
`manifest.json` 指向這些檔案。

不要宣告與檔案不符的 `sizes`。
