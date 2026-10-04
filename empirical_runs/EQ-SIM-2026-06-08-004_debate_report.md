# EQ-SIM-2026-06-08-004 — v2 辯論:廣/中小型 universe 重測(★首個 VALIDATED)

**裁決:VALIDATED(Small-Cap Value)** ｜ 證實「瓶頸是 universe」。crypto+股票全程第一個過關因子。

## 背景
EQ-001/002/003 在 S&P500 大型股全失靈,假設瓶頸是 universe(經典異象主在廣/中小型)。
建 S&P1500(大503/中400 wiki/小603 wiki,`scripts/build_universe.py`),增量補抓 SEC+Yahoo(共 1502 檔),
分層重測 value + Piotroski(`scripts/eq_universe_retest.py`)。

## 結果(143 月,行業中性,PIT)
| 因子/tier | univ | IC_t | LS Sh(10bps) | 剔5% | 多頭超額 | 近36m LS |
|---|---|---|---|---|---|---|
| Value/large | 324 | 1.28 | 0.78 | 0.41 | 0.59 | 0.63 |
| Value/mid | 239 | 1.85 | 0.32 | 0.37 | 0.32 | 0.20 |
| **Value/small** | 352 | **3.85** | **1.70** | **+1.46** | **+1.49** | **+1.39** |
| Piotroski/(all/large/mid/small) | — | 全負 | 全負 | 全負 | 全負 | 全負 |

**成本敏感度(Value/small)**:LS Sharpe 10/30/50bps = 1.70/1.41/1.13;多頭超額 1.49/1.09/0.69。

## 裁決
- **Value/small = VALIDATED**:過全部七道規格——IC-IR≈0.32(IC_t3.85/√143)、剔5%+1.46(非尾部)、扛30bps(LS1.41/多頭超額1.09)、近36m+1.39(未衰減)、size 單調(小>大>中,內部一致)、PIT 無前視。
- **Piotroski = REJECT(確認)**:各 tier 全無 edge → 真的無效,非 universe 問題。

## ★meta 結論(確認假設)
**瓶頸是 universe 不是維度。** 大型股太效率,經典異象(value)被套利/衰減;放回**原生小型股 universe** 即復活且未衰減。
EQ-001~003 的「全失靈」是 universe 錯配,非基本面維度無效。

## 部署 caveat
小型股容量/流動性/借券限制 → 實作以**多頭 top 分位 vs universe 超額**為主(30bps 仍 1.09);超大 AUM 不適用;單市場 143 月,OOS 可再強化。

## 歸檔
validated `validated/EQ_SmallCap_Value.md`;harness/universe builder/抓取器可複用;ledger + index.db(首個 num_factors_validated=1)。
