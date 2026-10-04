# SIM-2026-06-09-016 — v2 辯論:衍生品定位策略(多空帳戶比/OI/頂級交易者)

**裁決:REJECT(全四策略)** ｜ crypto 階段 CLOSED 後的補測(用戶要求 TradingView MCP + 四指標)。

## 背景
用戶要求接 `tradesdontlie/tradingview-mcp` 做「多空帳戶比/OI/融資費率OI/強平量」策略。
**MCP 查證**:它是 TradingView 桌面圖表/Pine 自動化工具(78 工具),**不供這些衍生品資料、無歷史匯出** → 不適用。
**正確資料源**:`data.binance.vision /futures/um/daily/metrics`(免費全史)→ 多空帳戶比(global/top-trader account)、頂級持倉比、OI、taker 比。
funding 已有全史;**強平量免費拿不到**(Binance 下架公開端點,需 Coinglass 付費)。
抓 BTC 2022-2026 日線(1619 日,`scripts/fetch_deriv_metrics.py` → `empirical_runs/deriv_btc.pkl`)。
策略 `core.signals.FSIM_Deriv_Positioning`;harness `onchain_eval.py`(lag 防前視/剔5%/regime/打平)。

## 結果(10bps, lag=1)
| 策略 | net Sharpe | t | 剔最高5%日 | 判定 |
|---|---|---|---|---|
| 散戶反向(global L/S contrarian) | 0.735 | 1.49 | **−2.58** | 肥尾/不顯著/2023單年撐 |
| 跟單頂級交易者(top position) | −0.657 | −1.33 | −3.84 | 方向錯 |
| 聰明錢-散戶背離 | 0.059 | 0.12 | −3.31 | 無 edge |
| OI 突破 | −0.065 | −0.13 | −3.35 | 無 edge |

**散戶反向深掘**:毛 Sharpe 1.06 但**剔5%日 −2.15(連毛利都尾部撐)**;**lag2 Sharpe 0.033**(崩,lag 脆弱);年度 2023 +2.25 vs 其他 0~0.6。

## 裁決
**全 REJECT。** 多空帳戶比(唯一未測過者)= funding(SIM-008)+ whale(SIM-013)綜合死法:尾部集中 + 不顯著 + regime 依賴 + lag 脆弱。其餘三策略無 edge 或方向錯。

## 核心發現
crypto 衍生品定位資料(多空比/OI/頂級交易者)**仍無 robust harvestable alpha**——與已證偽的 funding/訂單流/鏈上同族(事件/尾部/延遲)。crypto 維度進一步被探盡。
**MCP 教訓**:接資料前先查它到底供什麼;TradingView MCP 是圖表自動化,非資料源。

## 歸檔
資料 `deriv_btc.pkl`(可複用,3指標全史)+ `fetch_deriv_metrics.py`;策略模組;ledger + index.db。validated 仍僅 Small-Cap Value。
