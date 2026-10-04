# SIM-2026-06-10-017 — v2 辯論:BTC/ETH Overnight/Weekend 時段季節性

**裁決:REJECT** ｜ crypto 日內搜尋樹(含季節性窗口)正式全關閉。

## 0. 預登錄(跑前對齊,未搬龍門)
外部證據(Quantpedia/Falkenstein/Bespoke/NGHT ETF)宣稱 BTC 報酬集中於美股盤外。
confirmatory、僅兩個文獻窗口(盤外、週五收→週一開)、不掃參數格。判準:
① 盤外 t≥2 且盤外−盤中差 t≥2,家族 4 檢定 Bonferroni |t|>2.50
② taker 5bps/邊淨 Sh>0;maker 2bps/邊 ≥1.0 或 vs HODL 雙贏(Sh 更高且 MaxDD 更小)
③ 剔最高 5% 盤外日仍正(毛與淨) ④ IS/OOS 同向 + ETF 後(2024-01-11→)仍正
⑤ BTC/ETH 同向 ⑥ 延遲 30min 穩健 ⑦ 不翻號。敗 ①/③/④/⑤ 任一 = REJECT。

## 1. Builder
- 資料:data.binance.vision 30m spot 全史(2017-08→2026-05,BTC/ETH 各 ~153,800 bars,
  `fetch_intraday_full.py` → `{btc,eth}_30m_full.parquet`)。
- 時段:`pandas-market-calendars` NYSE 真實日曆(DST/假日/半日);成交=邊界後第一根 30m bar 開盤。
- harness:`overnight_seasonality_eval.py`。2,218 交易日,485 個週末窗。

## 2. Empiricist(全真實,雙成本情境)
| 指標 | BTC | ETH |
|---|---|---|
| 盤外均值 / t | +20.7bps / **2.80**✓ | +28.0bps / **2.86**✓ |
| 盤中均值 / t | +1.0bps / 0.2 | −4.7bps / −0.79 |
| 盤外−盤中差 t | 2.16 | 2.79 |
| 週末窗 t(Bonf 2.50) | 1.78 ✗ | 2.09 ✗ |
| HODL Sh / MaxDD | 0.82 / −0.83 | 0.68 / −0.94 |
| 盤外淨 Sh @0/2/5bps邊 | 0.94/0.76/0.49 | 0.96/0.82/0.62 |
| **剔最高5%盤外日(毛)** | **−1.31** ✗✗ | **−1.25** ✗✗ |
| IS/OOS @5bps | 0.59/0.36 ✓同向 | 0.87/0.27 ✓同向 |
| 年度淨均值符號 | 2018/2022/2026 負 | 同 | 
| ETF 後淨 Sh / t | 0.69 / 1.06 ✗不顯著 | 0.70 / 1.08 ✗ |
| 延遲30min @maker | 0.68 | 0.73 |

## 3. Skeptic / Risk
- **溢酬=尾部事件**:top 5%(111/2218 天)扛起全部盤外報酬,剔掉後連零成本都深負
  → 與 funding(008)/whale(013)同款族C死法;「均值顯著」是少數暴漲夜的算術,不是連續 edge。
- regime 翻覆:熊市年(2018/2022)與 2026 YTD 皆負 → 它只是「牛市的 beta 集中在夜裡」。
- BTC maker 情境(0.76)輸 HODL(0.82):連最便宜執行都跑不贏躺著。
- 外部 NGHT ETF 類產品的敘事(ETF 後強化)在子樣本不顯著(t≈1.07)。

## 4. Arbiter 裁決
**REJECT**(敗③——兩資產;敗④年度穩定;BTC 敗②;週末窗敗①)。
不翻號、不改測盤中、不挑子窗口。

## 5. meta:crypto 日內研究正式收官
價量反轉(010/011/012)、ICT(FVG 打假)、訂單流(011/012)、衍生品定位(016)、
時段季節性(017)全證偽。死法地圖:族B(換手×成本)+族C(尾部集中)覆蓋全部日內候選。
**剩餘日內路徑只有付費資料(L2/清算)+ maker 基礎設施,超出本系統範圍。**

## 6. 歸檔
ledger +1(35 條);graveyard/FSIM_Overnight_Seasonality.md;index.db +session;
資料資產:`{btc,eth}_30m_full.parquet`(30m 全史,可複用)。
