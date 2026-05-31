#!/usr/bin/env python3
"""Write paper_insights for 3 newly-extracted papers."""
import sys
sys.path.insert(0, '/home/anson/factor-lab')
from core.memory import record_paper_insight

# Paper 1: GeomHerd
rid = record_paper_insight(
    paper_id='arXiv:2605.11645',
    paper_title='GeomHerd: Ricci Flow Herding Quantification',
    insight_type='research_direction',
    insight=(
        '新因子方向「微觀結構曲率塌縮指數(MCCI)」：'
        '以委託簿不平衡時序變化或COT持倉跨交易者相關性作為代理人互動圖代理，'
        '計算簡化版Ollivier-Ricci曲率塌縮訊號。'
        '主要偵測器提前272步發出羊群效應預警。'
        '輔助指標「有效詞彙量收縮」可直接用於價格模式熵追蹤。'
        '可作為SuperTrend+ADX+Vol策略的降倉/避險預警層。'
    ),
)
print(f'[1] research_direction: {rid}')

rid = record_paper_insight(
    paper_id='arXiv:2605.11645',
    paper_title='GeomHerd: Ricci Flow Herding Quantification',
    insight_type='architecture_reference',
    insight=(
        'Ollivier-Ricci曲率塌縮作為前瞻性羊群效應指標：'
        'k=1-W/d追蹤代理人互動圖拓撲變化。'
        '理論上建立圖論度量與CSAD的mean-field bridge。'
        '跨域驗證成功(Vicsek)。'
        '限制：需代理人層級數據(替代:委託簿/持倉)，大規模圖計算成本高。'
    ),
)
print(f'[2] architecture_reference: {rid}')

# Paper 2: BacktestBench
rid = record_paper_insight(
    paper_id='arXiv:2605.17937',
    paper_title='BacktestBench: LLM Automated Backtesting Benchmark',
    insight_type='architecture_reference',
    insight=(
        'AutoBacktest三代理架構(Summarizer->Retriever->Coder)'
        '可作為factor-lab因子自動化回測子系統設計藍圖。'
        '18246 QA pairs涵蓋四類任務。'
        '關鍵發現：grounded verification + standardized indicator reps是性能瓶頸。'
        '建議在empiricist驗證前加入SQL接地檢查層，建立統一Factor DSL。'
    ),
)
print(f'[3] architecture_reference: {rid}')

# Paper 3: Sequential Structure (negative result)
rid = record_paper_insight(
    paper_id='arXiv:2605.17724',
    paper_title='Sequential Structure: LSTM vs GB on MNQ Futures',
    insight_type='design_constraint',
    insight=(
        '經驗下界：4年單標的5分鐘OHLCV不足以支撐可靠時序ML日內預測。'
        '最佳模型OOS準確率50.89% < 基準率51.8%，排列檢定p=0.135不顯著。'
        'WF特徵重要性極不穩定，為噪聲擬合而非結構訊號。'
        '因子研究須引入：(a)跨標的橫截面數據(b)tick-level LOB(c)另類數據。'
        '佐證規則型因子(SuperTrend+ADX+Vol)在數據受限下比端到端ML更穩健。'
        '建議整合排列檢定和WF特徵重要性追蹤入empiricist驗證流程。'
    ),
)
print(f'[4] design_constraint: {rid}')

print('Done: 4 paper_insights written.')
