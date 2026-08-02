# apps/ — 刻意保持空的

本專案採**單一 multi-role PWA**，程式在 [`packages/frontend`](../packages/frontend)。
長者端、照護端、家屬端以 route 區分角色，不是三個獨立的應用程式。

文件 12 的骨架列了 `elder-web`／`care-web`／`family-web` 三個目錄，
已由 [ADR 0006](../docs/adr/0006-frontend-stack-and-app-topology.md) 取代並移除。

**不要把它們加回來。** 若確實需要拆分成獨立部署單元，先寫一份 ADR 推翻 0006。
