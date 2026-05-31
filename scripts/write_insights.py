#!/usr/bin/env python3
"""Write paper insights to the DB."""
import sys
sys.path.insert(0, '/home/anson/factor-lab')
from core.memory import record_paper_insight

# ========== 2604.20949 - Microstructure Regimes ==========
record_paper_insight(
    paper_id='2604.20949',
    paper_title='Early Detection of Latent Microstructure Regimes in Limit Order Books',
    insight_type='design_constraint',
    insight='回測框架必須量測 regime detection 的 lead-time（偵測時間減去壓力發生時間）。若 lead-time <= 0，則不具實戰價值。BTC/USDT 實證平均 lead-time = +38 ± 21 秒，傳統 OFI/波動率/價差 baseline 全部為負 lead-time。'
)

record_paper_insight(
    paper_id='2604.20949',
    paper_title='Early Detection of Latent Microstructure Regimes in Limit Order Books',
    insight_type='research_direction',
    insight='可探索以 L2/L3 訂單簿 depth erosion + HMM entropy 為核心的早期預警因子。BTC/USDT 實證顯示此組合解釋 >99% 首觸發。具體做法：監控 bid/ask depth 侵蝕速率，當 depth erosion 與 HMM entropy 同時上升時觸發預警。'
)

record_paper_insight(
    paper_id='2604.20949',
    paper_title='Early Detection of Latent Microstructure Regimes in Limit Order Books',
    insight_type='architecture_reference',
    insight='三狀態因果 regime 模型（stable → latent build-up → stress）可泛化至因子輪動與波動率 regime。轉移矩陣禁止 0→2 直接跳轉，搭配 CUSUM 觸發式偵測器（不確定性通道 + 漂移通道 + MAX 聚合）提供正 lead-time 理論保證。'
)

record_paper_insight(
    paper_id='2604.20949',
    paper_title='Early Detection of Latent Microstructure Regimes in Limit Order Books',
    insight_type='design_constraint',
    insight='MAX 聚合（取最差通道）在偵測任務中優於平均聚合。設計多通道 regime detector 時，應以「哪個通道先看到壓力」的 worst-case 邏輯取代「平均狀態」聚合。'
)

record_paper_insight(
    paper_id='2604.20949',
    paper_title='Early Detection of Latent Microstructure Regimes in Limit Order Books',
    insight_type='design_constraint',
    insight='SNR 與 lead-time 存在顯式關係：drift-to-noise ratio η > sqrt(2 log(1/δ) / T₁) 時預期 lead-time 為正（Proposition 1）。若實證 SNR 低於此閾值，應提高資料頻率以增加 SNR 或放棄 regime detection 策略。'
)

# ========== 2604.24366 - Polymarket Microstructure ==========
record_paper_insight(
    paper_id='2604.24366',
    paper_title='The Anatomy of a Decentralized Prediction Market: Microstructure Evidence from the Polymarket Order Book',
    insight_type='design_constraint',
    insight='任何使用 Polymarket 交易方向資訊的策略，必須從鏈上 OrderFilled 事件獲取方向，不可用公開 WebSocket feed 的 change_side 欄位。實證顯示 WebSocket 推斷方向與鏈上真實方向僅 ~59% 一致（基準隨機 50%），導致 effective half-spread 在 67% 市場翻號、Kyle lambda 在 60% 翻號。'
)

record_paper_insight(
    paper_id='2604.24366',
    paper_title='The Anatomy of a Decentralized Prediction Market: Microstructure Evidence from the Polymarket Order Book',
    insight_type='design_constraint',
    insight='Polymarket 低機率合約（p < 0.10）中位數半價差為 1,300-1,800 bps，作為訊號來源時應對低機率合約給予較低權重，或設定機率下限閾值過濾高交易成本合約。極端事件合約價格可能有顯著噪音。'
)

record_paper_insight(
    paper_id='2604.24366',
    paper_title='The Anatomy of a Decentralized Prediction Market: Microstructure Evidence from the Polymarket Order Book',
    insight_type='design_constraint',
    insight='Polymarket wash trading 下限估計中位僅 0.97%（p90=4.5%），遠低於加密代幣交易所 25-70%。此為 Polymarket 機率作為訊號來源的正面證據，但仍需在策略中監控個別市場的 self-match 比例。'
)

# ========== 2604.27041 - Signal Credibility Index ==========
record_paper_insight(
    paper_id='2604.27041',
    paper_title='The Signal Credibility Index for Prediction Markets: A Microstructure-Grounded Diagnostic',
    insight_type='architecture_reference',
    insight='SCI = PR × (1-TS) × (1-HHI^flow)，PR 為持久性比率（bounded [0,1]，PR=1 表示所有增量同號的單調移動，替代傳統 variance ratio），TS 為雙邊性指數，HHI^flow 為衝擊後交易者回應集中度。三成分 SCI 在 Monte Carlo 四種 regime 分類中 AUC=0.984。可直接用於 Polymarket 策略過濾暫態流動性壓力造成的假訊號。'
)

record_paper_insight(
    paper_id='2604.27041',
    paper_title='The Signal Credibility Index for Prediction Markets: A Microstructure-Grounded Diagnostic',
    insight_type='design_constraint',
    insight='所有預測市場價格變動計算應在 logit 空間進行（ℓ_t = log(p_t/(1-p_t))），確保 p 和 1-p 的移動對稱等價。傳統 variance ratio 在短窗口有分母為零問題，應改用 bounded [0,1] 的 Persistence Ratio（PR）。'
)

record_paper_insight(
    paper_id='2604.27041',
    paper_title='The Signal Credibility Index for Prediction Markets: A Microstructure-Grounded Diagnostic',
    insight_type='research_direction',
    insight='可探索將 SCI 三成分框架（PR + TS + HHI^flow）遷移至加密貨幣訂單簿資料，區分真正的趨勢延續 vs 大戶短期操縱。Cobb-Douglas 加權形式允許按場景調整權重：HFT 場景加重 PR（α₁=1.5），政治預測市場加重 HHI^flow（α₃=1.5）。'
)

# ========== 2605.01176 - SPO Portfolio Optimization ==========
record_paper_insight(
    paper_id='2605.01176',
    paper_title='Decision-Induced Ranking Explains Prediction Inflation and Excessive Turnover in SPO-Based Portfolio Optimization',
    insight_type='design_constraint',
    insight='若在因子發掘+組合構建 pipeline 中使用 DFL（Decision-Focused Learning）端到端訓練，必須內建預測尺度約束。SPO 訓練的線性預測器會自發膨脹預測值（組合優化本質是排序問題），導致月度單邊換手高達 0.96。三種干預：(1) clipping 截斷至 [-0.1, 0.1]；(2) min-max rescaling 保留截面排序壓縮至 [-c, c], c=0.1；(3) partial adjustment 權重指數平滑 w_t = α w*_t + (1-α) w_{t-1}。'
)

record_paper_insight(
    paper_id='2605.01176',
    paper_title='Decision-Induced Ranking Explains Prediction Inflation and Excessive Turnover in SPO-Based Portfolio Optimization',
    insight_type='design_constraint',
    insight='SuperTrend 產生離散交易訊號（非連續預測值）天然避開了 SPO 預測膨脹問題。但若後續導入 ML 模型產生連續分數餵給 MVO 優化器，必須先應用 partial adjustment 控制換手，再考慮 clipping 或 rescaling 約束預測尺度。'
)

# ========== 2605.04004 - OHLCV Falsification ==========
record_paper_insight(
    paper_id='2605.04004',
    paper_title='Structural Limits of OHLCV-Based Intraday Signals in MNQ Futures: A Systematic Falsification Study',
    insight_type='design_constraint',
    insight='OHLCV-only 策略在 5 分鐘頻率已達結構性飽和。2021-2025 MNQ 期貨實證：所有訊號配置的 OOS p-value > 0.05，permutation test 確認最佳表現可在隨機標籤下複製。日內 alpha 必須整合微結構資料（order book depth, trade flow, liquidity consumption），純 OHLCV 無法突破資訊理論天花板。'
)

record_paper_insight(
    paper_id='2605.04004',
    paper_title='Structural Limits of OHLCV-Based Intraday Signals in MNQ Futures: A Systematic Falsification Study',
    insight_type='design_constraint',
    insight='回測驗證框架必須加入系統性證偽程序：(1) permutation test 隨機打亂標籤；(2) HPO 穩定性分析（walk-forward 各折之間最優超參數是否穩定）；(3) sample selection robustness。目前的 rolling walk-forward 僅驗證穩定性，未系統排除 confounds。'
)

# ========== 2605.00854 - Cubic Momentum ==========
record_paper_insight(
    paper_id='2605.00854',
    paper_title='Dynamics of Periodic Bubbles and Crashes: Modeling Market Overheating and Panic Selling via Cubic Momentum',
    insight_type='research_direction',
    insight='可設計 Cubic Momentum Indicator：CMI_t = (M_t - a)(M_t - b)(M_t - c)，其中 M_t = Σ e^{-r(t-s)} (log P_s - log P_{s-1}) 為指數加權動量，參數 a<b<c 為三次函數的三個根。CMI > 0 跟隨趨勢，CMI 轉負（動量超越臨界閾值 b）時平倉/反轉。此框架比 ADX 單純值域過濾更動態，內建動量進入危險區的相變邏輯。'
)

record_paper_insight(
    paper_id='2605.00854',
    paper_title='Dynamics of Periodic Bubbles and Crashes: Modeling Market Overheating and Panic Selling via Cubic Momentum',
    insight_type='architecture_reference',
    insight='Hawkes 內生交易頻率 λ_t = Λ + kM_t（Λ 為基礎交易機率，k 為動量敏感度）可作為成交量預警輔助確認：上漲末段成交量激增意味著接近崩盤相變點，可做為出場訊號的輔助確認。'
)

print("Done. All insights written.")
