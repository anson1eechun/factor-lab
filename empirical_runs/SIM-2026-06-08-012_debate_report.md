# SIM-2026-06-08-012 — v2 辯論:日內訂單流 CVD(動量/背離)

**裁決:REJECT** ｜ 訂單流維度(日內)實測,確認與日線(SIM-011)同結論:訊號=反轉、微結構/尾部驅動、不可收割。

## 背景
承 SIM-011 建議「訂單流真棲地在日內」。資料:BTC/ETH `{15m,1h,4h}` 訂單流
(`{asset}_flow_{tf}.pkl`,K線 taker_buy)。CVD=cumsum(2·taker_buy−vol)。

## 角色
- **Proposer**:① CVD 動量(主動買盤累積→續勢)② CVD–價背離(價漲流弱→反轉)。日內微結構為 flow alpha 自然棲地。
- **Builder**:`core.signals.FSIM_CVD_Intraday` → `cvd_mom`(CVD 斜率 tanh-z)、`tfi_rev`(近 bar 主動買壓 z 反向)。harness=`scripts/intraday_strategy_eval.py`(net_sharpe/剔最高5%bar/換手/曝險)。
- **Empiricist(標準套餐,全真實回測)**:

**① CVD 動量(cvd_mom)— 無 edge / 方向錯**

| asset/tf | net Sharpe(5bps) | 剔最高5%bar |
|---|---|---|
| BTC 15m | −16.1 | −51.6 |
| BTC 1h | −3.9 | −20.8 |
| BTC 4h | −0.6 | −8.8 |
| ETH 15m | −9.7 | −46.3 |
| ETH 4h | −0.2 | −9.0 |

→ 各時框淨值皆負,CVD 動量不存在;若有偏向反而是反動量,且被成本碾壓。

**② TFI 反轉(tfi_rev)— 毛利亮眼但是微結構假象**

| asset/tf | 毛 Sharpe(0bps) | 剔最高5%bar | 淨 Sharpe(5bps) | 打平成本 | 換手/bar |
|---|---|---|---|---|---|
| BTC 15m | **+6.51** | **−23.07** | **−39.71** | 0.69 bps/邊 | 0.68(近每 bar 翻) |
| ETH 15m | +1.78 | −25.75 | −32.35 | 0.26 bps/邊 | 0.66 |
| BTC 1h | +0.75 | −13.77 | −8.92 | 0.39 bps/邊 | 0.65 |
| ETH 1h | +0.21 | −14.04 | −6.91 | 0.15 bps/邊 | 0.63 |

→ 毛 Sharpe +6.5 **完全來自最高 5% bar(剔除→−23)**;曝險 0.996、近每 bar 翻倉。
這是 **bid-ask bounce**:bar 收盤被主動買盤推高 → 下一 bar 在價差內回彈;close 同時用於訊號與報酬 → 看得到吃不到。

- **Risk**:近每 bar 翻倉 → 容量≈0;純微結構雜訊,對 book 無增量。
- **Skeptic**:+6.5 毛利是價差內回彈假象;**打平成本 0.15–0.69 bps/邊**,實際 taker ~4–5bps+滑價 → 結構性必虧。
- **Arbiter(獨立)**:**REJECT**。CVD 動量無 edge;TFI 反轉非可交易(打平 <1bp、剔尾深負)。
  日內**確認** SIM-011 日線發現:**訂單流訊號=反轉、尾部/微結構驅動、不可收割**。

## 核心發現(meta)
**訂單流維度(日線 SIM-011 + 日內 SIM-012)已測盡:確認無可收割 alpha。**
- 真訊號一律為**反轉**,且越細時框越強 → 換手/成本越凶。
- 毛利集中在尾部/價差內回彈,**打平成本 <1bp**,零售與機構皆吃不到。
- 與 SIM-007(MAX)/009(殘差反轉)同族:**crypto 價量/流量維度的真訊號 = 不可套利的反轉**。

**下一條未測路徑**:鏈上維度(交易所淨流/清算)——免費起點 `ErcinDedeoglu/crypto-market-data`(BTC 時序)、Coinglass 清算史。
那是與「價量/流量反轉」正交的**基本面供給**訊號,可能避開反轉/微結構陷阱。

## 歸檔
- 因子:`core/signals/FSIM_CVD_Intraday.py`(deprecated)
- 墓誌:`graveyard/FSIM_CVD_Intraday.md`
- ledger +1;index.db sessions/rounds/transcripts +1
