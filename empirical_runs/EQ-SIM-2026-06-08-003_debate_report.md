# EQ-SIM-2026-06-08-003 — v2 辯論:Piotroski F-score(美股品質)

**裁決:REJECT(大型股無 edge)** ｜ 股票延伸第三輪。

## 背景
價值族(value/資產成長)在大型股失靈後,轉品質複合 Piotroski F-score(9項財報健康度)。
排除金融/地產(無分類資產負債表);逐年算YoY,PIT按10-K filed≤T;月頻行業中性。harness `scripts/eq_piotroski_eval.py`。

## 結果(132月,行業中性)
| | rank-IC | IC_t | LS Sharpe(t) | 剔5% | 多頭超額 |
|---|---|---|---|---|---|
| F-score | −0.0022 | **−0.21** | −0.40(−1.34) | −0.87 | −0.36 |

分段 IC_t:前 −0.30、中 −0.14、近 +0.25;近24m +0.06 → **全程 IC≈0**。universe 僅 146。

## 裁決
**REJECT。** 財報健康度在 S&P500 大型股無預測力——Piotroski 原為**便宜/中小型股**內部分辨好壞而設計,大型股皆被充分分析的健康公司,訊號已被定價。

## ★三輪 meta 結論:瓶頸是 universe 不是維度
- EQ-001 value:衰減(IC→0)
- EQ-002 資產成長:反轉(REJECT)
- EQ-003 Piotroski:無 edge(REJECT)

三個經典基本面異象在 **S&P500 大型股 2014-26** 全失靈,共同原因:
1. **universe 不匹配**:這些異象 documented 在**廣/中小型/價值傾斜** universe;大型股太效率、被分析到透。
2. **regime**:2014-26 成長主導,壓制價值族。

→ **問題不在「基本面」這個維度,而在「S&P500 大型股」這個 universe 太效率。** 要讓基本面研究有救,需**更廣/含中小型的 universe**(Russell 2000 / 全美上市)。SEC(10400 檔)+ Yahoo 技術上能做全美上市,只缺一份「流動但含中小型」的成分清單與市值過濾。

## 歸檔
harness 可複用;ledger + index.db(EQ-SIM-003)。下一步建議:EQ-SIM-004 換 universe——建「廣/中小型」清單,把已掛的 value/Piotroski 放回它們原生 universe 重測(驗證是否真為 universe 問題)。
