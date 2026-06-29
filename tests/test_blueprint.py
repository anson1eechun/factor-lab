"""Nyrobrain 藍圖新模組的回歸/不變量測試（Phase 0–4 + honesty 護欄 + direction 推斷）。

跑：uv run --with pytest --with "numpy>=2" --with pandas --with pyyaml python -m pytest tests/test_blueprint.py -q
"""
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from core import data as D            # noqa: E402
from core import signal_models as SM  # noqa: E402
from core import backtest as BT       # noqa: E402
from core import kb_graph as KG       # noqa: E402
from core import memory as MEM        # noqa: E402


# ───────────────────────── core.data ─────────────────────────
def test_data_available_and_load():
    assert len(D.available()) == 13
    s = D.load("coinbase_premium_gap")
    assert len(s) > 1000
    assert s.index.is_monotonic_increasing
    assert not s.index.has_duplicates


def test_data_alias_resolution():
    n = len(D.load("coinbase_premium_gap"))
    assert len(D.load("btc_coinbase_premium_gap")) == n
    assert len(D.load("coinbase_premium_gap.json")) == n


def test_data_missing_raises():
    with pytest.raises(FileNotFoundError):
        D.load("no_such_series_xyz")


def test_profile_basic_signs():
    p = D.profile_basic("exchange_netflow")
    assert p["has_negative"] is True and p["n"] > 1000


def test_data_dictionary():
    dd = D.data_dictionary()
    assert len(dd) == 13
    e = dd["btc_coinbase_premium_gap"]
    assert "trading_signal" in e and "n" in e


# ─────────────────────── core.signal_models ───────────────────────
def test_models_range_index_nonan():
    s = D.load("mvrv_ratio")
    for fn in SM.MODELS.values():
        pos = fn(s)
        assert pos.index.equals(s.index)
        assert pos.notna().all()
        assert float(pos.min()) >= -1.0 and float(pos.max()) <= 1.0


def test_data_profile_recommends_valid_model():
    for stem in D.available():
        assert SM.data_profile(D.load(stem))["recommended_model"] in SM.MODELS


def test_auto_signal_all_series():
    for stem in D.available():
        pos = SM.auto_signal(D.load(stem))
        assert pos.between(-1, 1).all() and pos.notna().all()


def test_direction_flip_symmetry():
    s = D.load("coinbase_premium_gap")
    a, b = SM.sign_flow(s, direction=1), SM.sign_flow(s, direction=-1)
    assert ((a + b).abs() < 1e-9).all()  # b == -a


# ───────────────────────── core.backtest ─────────────────────────
def _toy_px(n=60, step=0.01):
    idx = pd.date_range("2023-01-01", periods=n, freq="D")
    return pd.Series([100 * (1 + step) ** i for i in range(n)], index=idx)


def test_evaluate_positions_uptrend_long():
    px = _toy_px()
    m = BT.evaluate_positions(pd.Series(1.0, index=px.index), px, cost_bps=0, lag=0)
    assert m["ann_return"] > 0 and m["net_sharpe"] > 0  # 多頭吃上漲
    assert m["exposure"] == 1.0
    assert "position" in m and "net_returns" in m


def test_grid_optimize_plateau_and_heatmap():
    px = BT.load_btc_price()
    s = D.load("coinbase_premium_gap")
    g = BT.grid_optimize(lambda w: SM.sign_flow(s, w=int(w), direction=1), {"w": [10, 20, 30, 40]}, px)
    assert g["best_params"] is not None
    assert 0.0 <= g["plateau_score"] <= 1.0 and 0.0 <= g["positive_frac"] <= 1.0
    g2 = BT.grid_optimize(
        lambda w, k: SM.breakout_spike(D.load("long_liquidations_usd"), w=int(w), k=float(k)),
        {"w": [20, 30], "k": [2.0, 3.0]}, px)
    assert "heatmap" in g2 and len(g2["heatmap"]["z"]) == 2


def test_rolling_walk_forward_keys():
    px = BT.load_btc_price()
    s = D.load("coinbase_premium_gap")
    wf = BT.rolling_walk_forward(lambda w: SM.sign_flow(s, w=int(w), direction=1),
                                 {"w": [20, 30, 40]}, px, train_days=365, test_days=180)
    assert wf["n_folds"] >= 1
    for k in ("cv_sharpe", "positive_folds", "oos_max_drawdown", "folds"):
        assert k in wf


def test_norm_ppf_cdf():
    assert abs(BT._norm_ppf(0.975) - 1.959964) < 1e-3
    assert abs(BT._norm_cdf(0.0) - 0.5) < 1e-9
    assert abs(BT._norm_cdf(BT._norm_ppf(0.3)) - 0.3) < 1e-4


def test_deflated_sharpe_range_and_monotone():
    import random
    random.seed(1)
    idx = pd.date_range("2022-01-01", periods=400, freq="D")
    rets = pd.Series([0.001 + 0.01 * (random.random() - 0.5) for _ in range(400)], index=idx)
    narrow = BT.deflated_sharpe(rets, sr_trials_ann=[0.9, 0.95, 1.0])
    wide = BT.deflated_sharpe(rets, sr_trials_ann=[0.2, 0.9, 1.6, 2.2, -0.3, 0.5])
    assert 0.0 <= narrow["dsr"] <= 1.0 and 0.0 <= wide["dsr"] <= 1.0
    assert wide["dsr"] <= narrow["dsr"]  # 試更多/更雜 → 可信度更低


def test_pbo_range():
    import random
    random.seed(2)
    rets = [0.0005 + 0.01 * (random.random() - 0.5) for _ in range(200)]
    assert 0.0 <= BT.compute_pbo(rets) <= 1.0


# ───────────────────────── core.kb_graph ─────────────────────────
def test_build_graph_structure():
    g = KG.build_graph()
    ids = {n["id"] for n in g["nodes"]}
    assert "root" in ids
    assert g["stats"]["nodes"] > 0 and g["stats"]["edges"] > 0
    for e in g["edges"]:
        assert e["from"] in ids and e["to"] in ids  # 無懸空邊
    assert "vis-network" in KG.render_html(g)


# ──────────────────── core.memory 回饋迴路 ────────────────────
def test_deprecated_factors_nonempty():
    # 守 get_deprecated_factors 大小寫 bug 的修復（'REJECT' vs 'rejected'）
    assert len(MEM.get_deprecated_factors()) > 0


def test_proposer_priors_always_cites():
    assert "- " in MEM.proposer_priors(category="carry")
    assert "- " in MEM.proposer_priors(category="zzz_unseen_category")  # fallback 仍 ≥1


def test_graveyard_lessons():
    g = MEM.get_graveyard_lessons()
    assert isinstance(g, list)
    if g:
        assert "name" in g[0] and "lesson" in g[0]


# ─────────────── quick_research.infer_direction ───────────────
def test_infer_direction():
    from quick_research import infer_direction
    assert infer_direction("Positive → Bearish (Dump risk). Negative → Bullish.", "sign_flow")[0] == -1
    assert infer_direction("Wide positive gap → Institutional demand strong.", "sign_flow")[0] == 1
    assert infer_direction("", "sign_flow")[0] is None
    # 「Confirms bearish/bullish」第二句判決
    assert infer_direction("High spike → long pain. Confirms bearish trend.", "breakout_spike")[0] == -1
    assert infer_direction("High spike → short pain. Confirms bullish.", "breakout_spike")[0] == 1
    # 只描述「下降側」→ 反推高值側
    assert infer_direction("Declining trend → Bullish (removing supply).", "trend_drift")[0] == -1
    # 同句多空並陳 → 模稜 → None（不硬猜）
    assert infer_direction("High spike → panic selling or whale accumulation.", "percentile_rank")[0] is None
    bull = "Wide positive gap → demand strong."
    assert infer_direction(bull, "sign_flow")[0] == -infer_direction(bull, "zscore_reversion")[0]


def test_research_factor_smoke():
    from quick_research import research_factor
    R = research_factor("coinbase_premium_gap", log_ledger=False)
    assert R["direction"] in (1, -1)
    assert R["model"] in SM.MODELS
    for k in ("opt", "single", "wf", "dsr", "pbo", "contra", "rationale", "long_when"):
        assert k in R
    assert isinstance(R["wf"]["cv_sharpe"], float)


def test_universe_sweep_importable():
    import universe_sweep
    assert hasattr(universe_sweep, "main") and hasattr(universe_sweep, "_is_robust")


def test_evaluate_strategy_keys():
    px = BT.load_btc_price()
    s = D.load("coinbase_premium_gap")
    r = BT.evaluate_strategy(lambda w: SM.sign_flow(s, w=int(w), direction=1), {"w": [20, 30, 40]}, px)
    for k in ("opt", "best", "single", "wf", "dsr", "pbo"):
        assert k in r
    assert isinstance(r["wf"]["cv_sharpe"], float)


def test_regime_masks_causal():
    px = BT.load_btc_price()
    masks = SM.regime_masks(px)
    assert set(masks) == {"trend_up", "trend_down", "vol_high", "vol_low"}
    for m in masks.values():
        assert m.index.equals(px.index) and m.dtype == bool
    assert not (masks["trend_up"] & masks["trend_down"]).any()  # 趨勢上下不重疊


def test_condition_and_composite():
    s = D.load("coinbase_premium_gap")
    px = BT.load_btc_price()
    pos = SM.sign_flow(s, w=30, direction=1)
    cond = SM.condition_on_regime(pos, SM.regime_masks(px)["trend_up"])
    assert (cond.abs() > 0).sum() <= (pos.abs() > 0).sum()  # regime 外歸零 → 非零更少
    comp = SM.composite([SM.sign_flow(s, w=30, direction=1), SM.zscore_reversion(s, w=30, direction=1)])
    assert comp.between(-1, 1).all() and comp.notna().all()


def test_paper_trade_pnl():
    import paper_trade as pt
    rows = [{"date": "2026-06-29", "target_position": 1.0, "btc_close": 100.0},
            {"date": "2026-06-30", "target_position": 1.0, "btc_close": 110.0},
            {"date": "2026-07-01", "target_position": 0.0, "btc_close": 121.0}]
    net = pt._pnl(rows, 0)  # lag=1：今日持倉=昨日訊號；cost 0
    assert abs(net[0] - 0.1) < 1e-9 and abs(net[1] - 0.1) < 1e-9
