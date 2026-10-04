---
factor_id: FSIM_CVD
name: Intraday Order-Flow CVD (momentum / TFI reversal)
session: SIM-2026-06-08-012
verdict: REJECT
date: 2026-06-08
kind: 辯論模擬
data_dim: order-flow intraday (CVD / taker imbalance)
---

# Intraday CVD — REJECT

**機制**:① CVD=cumsum(2·taker_buy−vol) 動量 ② 近 bar 主動買壓反轉。BTC/ETH 15m/1h/4h。

**為何駁回**:
- **CVD 動量無 edge**:net Sharpe 各時框皆負(15m −16、4h −0.6),方向錯+成本碾壓。
- **TFI 反轉是微結構假象**:毛 Sharpe BTC15m +6.5 但**剔最高5%bar→−23**,近每 bar 翻倉(曝險0.996);
  **打平成本僅 0.15–0.69 bps/邊**,扣5bps→−40~−7。= bid-ask bounce(close 同用於訊號與報酬),吃不到。

**族譜**:確認 SIM-011(日線訂單流)→ 訂單流維度真訊號=反轉、尾部/微結構驅動、不可收割。同 SIM-007/009。

**下一路徑**:鏈上(交易所淨流/清算),正交於價量/流量反轉。
