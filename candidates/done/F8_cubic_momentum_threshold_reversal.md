---
date: 2026-05-26
status: candidate
category: momentum
formula: "M_t = EWM(log_ret, halflife=14); CMI_t = (M_t - a_t)(M_t - b_t)(M_t - c_t); a_t = rolling_252_quantile(M, 5%); b_t = rolling_252_quantile(M, 75%); c_t = rolling_252_quantile(M, 95%)"
implementation: core/signals/F8_cubic_momentum_threshold_reversal.py
hypothesis: 指數加權動量 M_t 跨越臨界閾值後進入「過熱區」，此時做市商與大戶開始減倉導致動量自我衰減 → 反轉。以三次多項式 CMI = (M-a)(M-b)(M-c) 內建相變邏輯，比 ADX 單純值域過濾更動態。
expected_effect: both
applicable_markets: [crypto]
derived_from: [[2605.00854-cubic-momentum]]
