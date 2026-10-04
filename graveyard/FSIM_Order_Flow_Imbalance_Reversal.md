---
factor_id: FSIM_OFIR
name: Order-Flow Imbalance Reversal
session: SIM-2026-06-08-011
verdict: REJECT
date: 2026-06-08
kind: 辯論模擬
data_dim: order-flow (taker buy/sell imbalance)
---

# Order-Flow Imbalance Reversal — REJECT

**機制**:taker 主動買賣失衡 TFI=(buy−sell)/vol(K線第9欄,免費),高 TFI → 次日相對走弱(橫截面反轉)。

**為何駁回**:訊號真實但不可收割。
- IC +0.0128 / t **+3.42**(顯著),但 **IC-IR 僅 0.10** < 0.3。
- 毛利 LS Sharpe +0.37(t0.66 不顯著);**剔最高5%日 → −2.13**(肥尾集中)。
- 換手 **2.96/日**,毛利 2.56bps/日,**打平成本上限 0.86bps/邊**;10bps 下淨 Sharpe **−3.90**,四年皆深負。

**族譜**:同 SIM-007(MAX)、SIM-009(殘差反轉)——crypto 真訊號多為反轉型、IC-IR≈0.1、成本/換手碾壓。

**殘值**:訂單流 alpha 真棲地在**日內微結構**(已備 btc/eth_flow_{15m,1h,4h}.pkl),日線非其場域。
