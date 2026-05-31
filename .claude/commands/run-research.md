---
description: 跑一輪因子辯論會（提出→建構→質疑→實證→仲裁→入庫）
---

主持一輪因子研究辯論，最多 config.yaml 的 `max_debate_rounds` 回合：

1. **proposer**：先讀 `10-因子库` 既有因子 + 文獻的「待提案線索」，提 1~3 個新因子。
2. 對每個候選，進入辯論回合：
   a. **builder** 寫成可計算函數（無前視偏誤）。
   b. **skeptic** 逐條質疑；builder/proposer 反駁或修正。
   c. **empiricist** 用 core/metrics.py 跑 Rank-IC / IC-IR / 分組 / 相關性。
   d. **arbiter** 裁決：validated / revise(退回 a) / deprecated。
3. **librarian** 把 validated/deprecated 因子入庫、去重、建連結、更新 MOC。
4. 彙報：本輪採納/否決了哪些因子、關鍵證據與理由。

鐵律：證據 > 口才；達回合上限仍未過 → deprecated。
