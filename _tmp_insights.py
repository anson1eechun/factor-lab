#!/usr/bin/env python3
"""批次寫入 10 篇論文核心洞見到 paper_insights DB"""
from core.memory import record_paper_insight

papers = [
    ("2604.26747", "From Hypotheses to Factors: Constrained LLM Agents in Cryptocurrency Markets",
     "Agentic因子發現須有嚴格審計協議：固定選擇閘門、不可變append-only實驗軌跡。"
     "假說與可執行配方分離是agent可信度關鍵。Crypto alpha存在但容量極小。"
     "append-only trace可作為factor-lab記憶模組設計參考。"),
    ("2605.12532", "AgenticAITA: Deliberative Multi-Agent Reasoning for Autonomous Trading Systems",
     "多代理辯論管線(分析師→風險官→執行官)可對應factor-lab Phase 2因子辯論設計。"
     "AZTE z-score觸發引擎只在市場異常時喚醒LLM節省認知資源。"
     "Agentic Friction指標作為系統健康度量化度量。IGP mutex鎖保證並行安全。"),
    ("2605.12977", "Enhancing a Risk Model by Adding Transient Statistical Factors",
     "在Barra基礎模型上以MLE+指數加權+EM算法疊加暫態統計因子，不修改原始因子載荷。"
     "EM框架自然處理缺失回報，適合crypto市場。"
     "建議MVO/risk parity回測使用低秩+對角結構取代rolling sample covariance。"
     "暫態因子概念可移植到crypto的exchange-level flow、鏈上活動尖峰等短壽命因子。"),
    ("2605.13407", "PRISM-VQ: Vector-Quantized Discrete Latent Factors Meet Financial Priors",
     "VQ資訊瓶頸作為噪音環境正則化特別有效(CSI 300 Sharpe 1.57)，直接關聯crypto高噪音市場。"
     "先驗因子+VQ學習因子混合架構可借鑒：用已知因子作穩定錨。"
     "結構條件MoE以VQ離散代碼做gating生成動態factor loading。"
     "離散代碼可作為market regime標籤，與波動率regime classifier結合。"),
    ("2605.11423", "A Validated Volatility-Volume-Gap Classifier for Regime Identification",
     "波動率+成交量+缺口三維度市場狀態分類可借鑒到crypto。"
     "全部結果OOS walk-forward驗證，此嚴謹方法應作為factor-lab因子評估標準。"
     "與既有SuperTrend ADX+Vol filter互補：可加入缺口維度。"),
    ("2604.23833", "Beyond De Prado and Cotton: Hierarchical and Iterative Methods for General MV Portfolios",
     "將HRP從風險平價擴展至一般mean-variance問題，引入迭代層次方法。"
     "對multi-factor組合權重分配有參考價值：可考慮以迭代層次MV取代單純等權。"),
    ("2603.14288", "Beyond Prompting: Autonomous Factor Investing via Agentic AI",
     "因子發現封閉迴圈五模組(假設生成→執行→評估→閘門→記憶)可直接對應factor-lab架構。"
     "最關鍵缺失模組是記憶與策略更新：可加入append-only軌跡避免重複無效假說。"
     "符號回歸生成可解釋數學公式優於黑箱NN。LightGBM非線性合成層組合多個agentic因子。"),
    ("2509.16206", "DRL-Factor-Investment-CAFPO: Conditional Autoencoder Factor Portfolio Optimization",
     "條件自編碼器將高維回報壓縮為低維潛在因子再以DRL學習組合映射，Sharpe 0.94。"
     "差分獎勵函數(差分Sharpe Ratio)解決Sharpe不可加總問題，可用於BTC/ETH訓練。"
     "條件自編碼思想可移植：用市場狀態(波動率體制、鏈上指標)條件化因子生成。"),
    ("2507.07107", "ML Enhanced Multi-Factor Quantitative Trading: Bias Correction",
     "Mask-first設計是本質創新：在因子計算前就剔除不可交易資產，消除漲跌停導致的18% IC膨脹。"
     "Mask合約貢獻+0.44 Sharpe(最大組件)。可直接用於crypto：交易所維護/代幣下架/流動性不足。"
     "Adjusted-MSE(方向錯誤懲罰11倍)比標準MSE更適合方向性交易。GPU向量化加速51倍。"),
    ("2604.18821", "Evaluating Structured Strategy Backtests: Peer Benchmarks, Regime Timing, Live",
     "1726檔結構化策略回測績效在實盤大幅衰減：回測反映因子順風而非策略技巧。"
     "所有回測應對照LOO peer benchmark折價評估。因子極端行情後發行的策略衰減更嚴重。"
     "我們的SuperTrend回測需檢驗：2020-2025是否恰好是趨勢策略順風期。"
     "發行後折扣：因子極端行情後應對回測打折。"),
]

for pid, title, insight in papers:
    rid = record_paper_insight(
        paper_id=pid,
        paper_title=title,
        insight_type='design_constraint',
        insight=insight,
    )
    print(f"OK: {pid} -> row {rid}")

print(f"\nTotal: {len(papers)} insights written")
