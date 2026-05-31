#!/usr/bin/env python3
"""
Tag Standardization Script for Quant Trading Knowledge Base.

1. Replace Chinese tags with standardized English equivalents
2. Auto-tag papers that lack topic tags based on title/content keywords
3. Remove or normalize workflow tags
"""
import yaml
import re
from pathlib import Path
from collections import Counter

BASE = Path('/home/anson/Documents/Obsidian Vault/量化交易/06-书籍论文')

# Chinese → English tag mapping (controlled vocabulary)
CN_TO_EN = {
    '風控': 'risk_management',
    '機器學習': 'machine_learning',
    '深度學習': 'deep_learning',
    '強化學習': 'reinforcement_learning',
    '强化学习': 'reinforcement_learning',
    '微觀結構': 'market_microstructure',
    '市場微結構': 'market_microstructure',
    '籌碼': 'order_flow',
    '金融AI': 'financial_AI',
    '選擇權定價': 'options_pricing',
    '隱含波動率': 'implied_volatility',
    '方法論': 'methodology',
    '因子挖掘': 'factor_mining',
    '语言模型': 'language_model',
    '宏觀': 'macro',
    '金融工程': 'financial_engineering',
    '可轉債定價': 'convertible_bond_pricing',
    '路徑相依': 'path_dependent',
    '跳躍模型': 'jump_model',
    '合成數據': 'synthetic_data',
    '非高斯': 'non_gaussian',
    '風險管理': 'risk_management',
    '資本配置': 'capital_allocation',
    '極值理論': 'extreme_value_theory',
    '保險精算': 'insurance_actuarial',
    '動能': 'momentum',
    '密度估計': 'density_estimation',
    '傅立葉方法': 'fourier_methods',
    '神經網路': 'neural_network',
    '厚尾分佈': 'fat_tailed_distribution',
    '最優執行': 'optimal_execution',
    '市場記憶': 'market_memory',
    '博弈論': 'game_theory',
    '投資組合執行': 'portfolio_execution',
    '暗池交易': 'dark_pool',
    '交叉交易': 'cross_trading',
    '偏好誘導': 'preference_elicitation',
    '因子籃子': 'factor_basket',
    '圖神經網路': 'graph_neural_network',
    '時間序列預測': 'time_series_forecasting',
    '幾何模式': 'geometric_patterns',
    '生成模型': 'generative_model',
    '合成資料': 'synthetic_data',
    '時間序列': 'time_series',
    '資料擴增': 'data_augmentation',
    '風險中性密度': 'risk_neutral_density',
    '無模型': 'model_free',
    '套利過濾': 'arbitrage_filtering',
    'Alpha挖掘': 'alpha_mining',
    '自演化智能体': 'self_evolving_agent',
    '遗传规划': 'genetic_programming',
    '共形推断': 'conformal_inference',
    '稳健控制': 'robust_control',
    '尾部风险': 'tail_risk',
    'Kelly准则': 'kelly_criterion',
    '对抗性学习': 'adversarial_learning',
    '可解释性': 'explainability',
    '监管合规': 'regulatory_compliance',
    '投资组合优化': 'portfolio_optimization',
    '稀疏性': 'sparsity',
    '决策聚焦学习': 'decision_focused_learning',
    '切线组合': 'tangency_portfolio',
    '几何学': 'geometry',
    '领域感知': 'domain_aware',
    '可持续投资': 'sustainable_investing',
    'LLM评估': 'LLM_evaluation',
    '偏差': 'bias',
    '基准测试': 'benchmarking',
    '立场文件': 'position_paper',
    '自监督学习': 'self_supervised_learning',
    '市场状态': 'market_regime',
    '表征学习': 'representation_learning',
    '波動率': 'volatility',
    '路径签名': 'path_signature',
    '资产配置': 'asset_allocation',
    '資產配置': 'asset_allocation',
    '粗糙路径理论': 'rough_path_theory',
    '論文索引': 'paper_index',
    '文献综述': 'literature_review',
    '自動生成': 'auto_generated',
    '動態規劃': 'dynamic_programming',
    '誤差傳播': 'error_propagation',
    '美国期权定价': 'american_option_pricing',
    '美式期權': 'american_option_pricing',
    '美式期权定价': 'american_option_pricing',
    '隨機控制': 'stochastic_control',
    '随机控制': 'stochastic_control',
    '数值方法': 'numerical_methods',
    '共形预测': 'conformal_prediction',
    '通用投资组合': 'universal_portfolio',
    '在线学习': 'online_learning',
    '分布自由': 'distribution_free',
    '覆盖理论': 'coverage_theory',
    '后悔界限': 'regret_bound',
    '并购套利': 'merger_arbitrage',
    '事件驱动': 'event_driven',
    '自然语言处理': 'NLP',
    '端到端學習': 'end_to_end_learning',
    '投資組合': 'portfolio',
    '隨機最優控制': 'stochastic_optimal_control',
    '蒙地卡羅': 'monte_carlo',
    '偏誤': 'bias',
    '前瞻偏誤': 'look_ahead_bias',
    '倖存者偏誤': 'survivorship_bias',
    '評測框架': 'evaluation_framework',
    '結構效度': 'structural_validity',
    '可解釋AI': 'explainable_AI',
    '金融監管': 'financial_regulation',
    '歐盟AI法案': 'EU_AI_Act',
    '錯誤': 'errata',
    '需重新下載': 'needs_redownload',
    '不確定性量化': 'uncertainty_quantification',
    '預測區間': 'prediction_interval',
    '無參數': 'nonparametric',
    '基因編程': 'genetic_programming',
    '自我進化': 'self_evolution',
    '量化金融': 'quantitative_finance',
    '論文合集': 'paper_collection',
    '文獻回顧': 'literature_review',
}

# Workflow/source tags to preserve but not treat as topic
WORKFLOW_TAGS = {'arxiv', '待精讀', 'ICML2026'}

# Keyword → tag mapping for auto-tagging based on title/content
TITLE_KEYWORD_TAGS = [
    (['volatility', '波動率', 'GARCH', 'variance', 'stochastic vol'], 'volatility'),
    (['option', 'option pricing', 'implied vol', 'American option', 'convertible bond pricing', 'black-scholes', 'Heston'], 'options_pricing'),
    (['risk', 'risk management', 'VaR', 'CVaR', 'tail risk', 'expected shortfall'], 'risk_management'),
    (['portfolio', 'portfolio optimization', 'black-litterman', 'mean-variance', 'asset allocation'], 'portfolio_optimization'),
    (['factor', 'alpha', 'factor investing', 'alpha mining', 'multi-factor'], 'factor_investing'),
    (['machine learning', 'deep learning', 'neural network', 'gradient boosting', 'random forest', 'XGBoost', 'LSTM', 'transformer'], 'machine_learning'),
    (['LLM', 'large language model', 'GPT', 'language model', 'agentic', 'agent', 'multi-agent'], 'LLM'),
    (['crypto', 'bitcoin', 'ethereum', 'DeFi', 'blockchain', 'cryptocurrency'], 'cryptocurrency'),
    (['forecast', 'prediction', 'time series', 'predicting'], 'time_series_forecasting'),
    (['execution', 'market impact', 'optimal execution', 'order', 'TWAP', 'VWAP'], 'optimal_execution'),
    (['microstructure', 'order book', 'L1', 'LOB', 'limit order', 'bid-ask', 'market making'], 'market_microstructure'),
    (['graph', 'GNN', 'graph neural', 'network'], 'graph_neural_network'),
    (['causal', 'causality', 'treatment effect', 'IV identification'], 'causal_inference'),
    (['pairs trading', 'statistical arbitrage', 'cointegration', 'mean reversion', 'market neutral'], 'statistical_arbitrage'),
    (['reinforcement learning', 'RL', 'DQN', 'PPO', 'policy gradient'], 'reinforcement_learning'),
    (['regime', 'market state', 'market regime', 'hidden markov', 'HMM'], 'market_regime'),
    (['ESG', 'sustainable', 'sustainability', 'carbon', 'green'], 'ESG'),
    (['insurance', 'actuarial', 'claim', 'annuity', 'mortality', 'underwriting'], 'insurance_actuarial'),
    (['prediction market', 'Polymarket', 'conditional', 'wagering'], 'prediction_market'),
    (['uncertainty', 'conformal', 'quantile', 'prediction interval'], 'uncertainty_quantification'),
    (['explain', 'interpretable', 'XAI', 'SHAP', 'LIME', 'feature importance'], 'explainability'),
    (['backtest', 'evaluation', 'benchmark', 'walk-forward', 'out-of-sample'], 'backtesting'),
    (['futures', 'perpetual', 'funding rate'], 'futures'),
    (['bond', 'fixed income', 'yield'], 'fixed_income'),
    (['copula', 'dependence', 'tail dependence', 'correlation'], 'dependence_modeling'),
    (['sentiment', 'news', 'NLP', 'text'], 'NLP'),
    (['high frequency', 'HFT', 'intraday', 'tick'], 'high_frequency_trading'),
    (['hedge', 'hedging', 'delta', 'gamma'], 'hedging'),
    (['bubble', 'crash', 'contagion', 'systemic risk', 'herding'], 'financial_stability'),
    (['benchmark', 'evaluation', 'dataset'], 'benchmarking'),
    (['privacy', 'noise', 'perturb', 'adversarial'], 'privacy'),
    (['bayesian', 'probabilistic', 'posterior', 'MCMC'], 'bayesian_methods'),
    (['off_policy', 'offline RL', 'batch RL'], 'offline_RL'),
    (['multi_agent', 'multi-agent'], 'multi_agent'),
    (['foundation model', 'foundation'], 'foundation_model'),
    (['operation', 'operational', 'production', 'deployment'], 'operational_ML'),
    (['arXiv', 'ICML', 'NeurIPS'], 'conference'),  # Will be skipped
]

def auto_tag_from_title(title):
    """Generate tags from paper title using keyword matching."""
    tags = set()
    title_lower = title.lower()
    for keywords, tag in TITLE_KEYWORD_TAGS:
        for kw in keywords:
            if kw.lower() in title_lower:
                tags.add(tag)
                break
    return tags


def process_file(filepath):
    """Process a single markdown file: standardize tags, auto-tag if needed."""
    text = filepath.read_text(encoding='utf-8')
    
    fm_match = re.search(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
    if not fm_match:
        return False, "no_frontmatter"
    
    try:
        fm = yaml.safe_load(fm_match.group(1))
    except Exception as e:
        return False, f"yaml_error: {e}"
    
    if not fm or 'tags' not in fm:
        return False, "no_tags"
    
    title = fm.get('title', '')
    tags = fm['tags']
    
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(',') if t.strip()]
    if not isinstance(tags, list):
        tags = [str(tags)]
    
    # Standardize: translate Chinese → English, normalize case
    std_tags = []
    has_topic = False
    for tag in tags:
        tag_s = str(tag).strip()
        if not tag_s:
            continue
        
        # Translate Chinese
        if tag_s in CN_TO_EN:
            tag_s = CN_TO_EN[tag_s]
        
        # Skip certain tags
        if tag_s.lower() in {'conference', 'paper_index', 'auto_generated', 
                               'needs_redownload', 'errata', 'paper_collection',
                               'position_paper'}:
            continue
        
        if tag_s not in std_tags:
            std_tags.append(tag_s)
            if tag_s not in WORKFLOW_TAGS:
                has_topic = True
    
    # If no topic tags, auto-tag from title
    if not has_topic and title:
        auto_tags = auto_tag_from_title(title)
        for t in sorted(auto_tags):
            if t not in std_tags:
                std_tags.append(t)
    
    # Reconstruct frontmatter with new tags
    fm['tags'] = std_tags
    
    # Rebuild the file
    new_fm = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False).strip()
    new_fm_block = f'---\n{new_fm}\n---'
    
    # Replace old frontmatter
    new_text = re.sub(r'^---\s*\n.*?\n---', new_fm_block, text, count=1, flags=re.DOTALL)
    
    if new_text != text:
        filepath.write_text(new_text, encoding='utf-8')
        return True, f"updated: {std_tags}"
    
    return True, "no_change"


def main():
    processed = 0
    updated = 0
    auto_tagged = 0
    errors = 0
    
    for md_file in sorted(BASE.rglob('*.md')):
        name = md_file.name
        if name in ('paper_insights.md', 'gap_analysis.md'):
            continue
        
        success, msg = process_file(md_file)
        processed += 1
        
        if not success:
            print(f'ERROR: {md_file.relative_to(BASE)} — {msg}')
            errors += 1
        elif 'updated' in msg:
            updated += 1
            rel = md_file.relative_to(BASE)
            if 'auto' in str(msg).lower() or True:  # print all updates
                print(f'UPDATED: {rel}')
    
    print(f'\n=== SUMMARY ===')
    print(f'Processed: {processed}')
    print(f'Updated:   {updated}')
    print(f'Errors:    {errors}')


if __name__ == '__main__':
    main()
