# SIM-2026-06-08-013 — v2 辯論:鏈上維度(交易所淨流 / 清算)

**裁決:REJECT** ｜ 第四個資料維度(鏈上)。失敗模式與前三個不同(非成本,而是尾部/regime/多重比較),但結論一致。

## 背景
價量/funding/訂單流三維度已證偽。本輪換**鏈上基本面供給**維度,正交於反轉族。
資料:`ErcinDedeoglu/crypto-market-data`(免費 BTC 日頻,CC BY 4.0,~1283 日 2022-12→2026-06),
存 `data/onchain/*.json`(交易所淨流/流入/流出/儲備/whale ratio/多空清算/穩定幣淨流/coinbase premium/MVRV/miner netflow…)。

## 角色
- **Proposer**:① 交易所淨流(幣進交易所=賣壓→看空)② 清算(連環爆倉=資本投降→反轉)③ whale/miner 充值=smart-money 賣壓。BTC 時序(單資產方向)。
- **Builder**:`core.signals.FSIM_Onchain_Supply`(whale_short / miner_short / supply_composite + 慢訊號變體);harness=`scripts/onchain_eval.py`(lag 防前視、含剔最高5%日壓測/年度regime/換手/打平)。
- **Empiricist(標準套餐)**:

**IC 掃描(level,vs 次日報酬,1280 日)**

| 訊號 | IC | t | 解讀 |
|---|---|---|---|
| **whale_ratio** | −0.065 | **−2.31** | 鯨魚充值→跌(最強) |
| **miner_netflow** | −0.055 | **−1.98** | 礦工充值→跌 |
| exchange_netflow | +0.055 | +1.96 | **符號與假設相反** |
| exchange_reserve | +0.054 | +1.92 | 同上(相反) |
| net_liq / long_liq / short_liq | ~0 | **\|t\|<1** | **清算無 edge** |

**方向策略淨值(10bps,lag=1)**

| 策略 | net Sharpe | t | 剔最高5%日 | 打平成本 | 年度 Sharpe |
|---|---|---|---|---|---|
| whale_short (z20) | 0.28 | 0.57 | **−3.24** | 13.9bps | 23/+1.5 24/−1.7 25/+1.6 亂跳 |
| whale_short (z90, 慢) | **0.75** | 1.53 | **−2.66** | **22.0bps** | 同樣不穩 |
| miner_short | −1.22 | −2.48 | −4.95 | 負 | 毛利方向錯 |
| supply_composite | −0.58 | −1.18 | −4.53 | 2.3bps | 全負 |

- **Risk**:whale 訊號換手低(0.37–0.51/日)、容量佳、與反轉族正交——**唯一不被成本殺的維度**;但邊際 Sharpe 不顯著。
- **Skeptic**:whale 慢訊號 Sharpe 0.75 看似可用,但 t=1.5、**剔最高5%日→−2.66**(正 Sharpe 全靠少數崩盤日)、年度符號亂跳;**37 假設多重比較下 Bonferroni t 門檻≈2.9,無一達標**。
- **Arbiter(獨立)**:**REJECT**。清算無 edge;交易所淨流/儲備符號與假設相反且不顯著;whale/miner 雖最強但 (a) 多重比較後不顯著 (b) 尾部集中 (c) regime 不穩。**正 Sharpe = 抓到少數崩盤日的尾部運氣,非穩健可收割 alpha**。

## 核心發現(meta)
**四個資料維度(價量 / funding / 訂單流 / 鏈上)全部證偽,但失敗模式分兩類:**
1. **價量/訂單流反轉族**(SIM-007/009/011/012):真訊號但**換手×成本碾壓**(打平<1bp)。
2. **funding/鏈上事件族**(SIM-008/013):**換手低、成本可活(打平 14–22bps)**,但**尾部集中+regime 不穩+多重比較不顯著**——正 Sharpe 全來自少數崩盤日。

→ **whale_ratio / miner_netflow / funding 動能 共同指向:這些是「崩盤風險」訊號,不是連續 alpha**。
建設性用途:**做風控 overlay**(whale 充值/funding 飆高 → 降槓桿/減碼),而非獨立多空策略。
(註:overlay-test 曾試 funding 減碼 overlay → 高 funding 預測續漲非崩盤,減碼反傷;whale 方向或許不同,可另測。)

**剔最高5%日壓測**至此已連續鑑別 6 個假陽性(007/008/009/011/012/013)——是本研究最有效的單一鑑別器。

## 歸檔
- 因子:`core/signals/FSIM_Onchain_Supply.py`(deprecated)
- 墓誌:`graveyard/FSIM_Onchain_Supply.md`
- 資料:`data/onchain/*.json`(13 指標,可重用);harness `scripts/onchain_eval.py`
- ledger +1;index.db sessions/rounds/transcripts +1
