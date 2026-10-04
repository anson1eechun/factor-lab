---
factor_id: FSIM_OCS
name: On-chain Supply / Liquidations (BTC time-series)
session: SIM-2026-06-08-013
verdict: REJECT
date: 2026-06-08
kind: 辯論模擬
data_dim: on-chain (exchange flows / liquidations / whale / miner)
---

# On-chain Supply / Liquidations — REJECT

**機制**:交易所淨流/儲備/whale ratio/miner netflow/清算/穩定幣淨流 → BTC 方向(賣壓看空)。
資料 `ErcinDedeoglu/crypto-market-data`(免費 BTC 日頻,~1283 日)→ `data/onchain/*.json`。

**為何駁回**:
- **清算無 edge**(net/long/short liq IC |t|<1)。
- 交易所淨流/儲備符號**與假設相反**(+IC)且不顯著。
- **whale_ratio 最強**(level IC −0.065/t−2.31)、miner_netflow t−1.98,但:
  - whale_short 慢訊號 net Sharpe 0.75 / **打平 22bps(不被成本殺)**,然 t=1.5 不顯著、
    **剔最高5%日→−2.66**(正 Sharpe 全靠少數崩盤日)、年度符號亂跳。
  - 37 假設多重比較 → Bonferroni t≈2.9,無一達標。

**族譜**:同 funding 動能(SIM-008)——換手低、成本可活,但尾部/regime/多重比較死。
**= 崩盤風險訊號,非連續 alpha**。建設性用途:風控 overlay(whale 充值→降槓桿),非獨立多空。

**資產**:`data/onchain/` 13 指標 + `scripts/onchain_eval.py` 可重用。
