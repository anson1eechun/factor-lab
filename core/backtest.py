"""因子回測層：包裝 AlphaPurify.FactorAnalyzer，為 Pipeline B 的 Empiricist 代理
提供 IC 分析、分層回測、績效報表。

支援兩種模式：
  1. 橫截面模式（多資產）：如 BTC/ETH/SOL/BNB 同時回測
  2. 時間序列模式（單資產）：回退到自訂 rank_ic + 簡單分層

用法：
    from core.backtest import FactorBacktest
    bt = FactorBacktest(df, factor_name="momentum_20")
    result = bt.run()
    bt.create_html_report("output.html")
"""

from __future__ import annotations
from typing import Optional
try:
    import polars as pl  # 僅用於型別註記；未安裝不阻斷 module 匯入（時序棧不需要）
except ModuleNotFoundError:
    pl = None
try:
    from alphapurify import FactorAnalyzer  # 橫截面棧（equity universe）；當前環境可能未裝
except ModuleNotFoundError:
    FactorAnalyzer = None


class FactorBacktest:
    """因子回測包裝器。

    對 AlphaPurify.FactorAnalyzer 的薄封裝，加上 factor-lab 的資料格式轉換
    和設定檔整合。
    """

    def __init__(
        self,
        df: pl.DataFrame,
        *,
        factor_name: str,
        trade_date_col: str = "datetime",
        symbol_col: str = "symbol",
        price_col: str = "close",
        fee_rate: float = 0.0009,     # 加密貨幣預設 0.09%/side
        slippage_rate: float = 0.0005,
        bins: int = 5,
        rebalance_periods: tuple = ("W", "M"),
        return_horizons: tuple = (1, 5, 10),
    ):
        """
        Args:
            df: Polars DataFrame，需含 datetime/symbol/close/{factor_name} 欄位
            factor_name: 要回測的因子欄位名稱
            trade_date_col: 交易日期欄位
            symbol_col: 資產代碼欄位
            price_col: 價格欄位
            fee_rate: 手續費率（每邊）
            slippage_rate: 滑點率
            bins: 分層組數
            rebalance_periods: 調倉週期 (W=週, M=月, Q=季)
            return_horizons: IC 觀測窗口（天）
        """
        self.df = df
        self.factor_name = factor_name
        if FactorAnalyzer is None:
            raise ImportError(
                "FactorBacktest 需要 alphapurify（橫截面/equity 棧），當前環境未安裝。"
                "時序/鏈上研究請改用 scripts/onchain_eval.py 或 core.backtest 的 "
                "grid_optimize / rolling_walk_forward。")
        self._fa = FactorAnalyzer(
            base_df=df,
            trade_date_col=trade_date_col,
            symbol_col=symbol_col,
            price_col=price_col,
            factor_name=factor_name,
        )
        # 覆蓋 ResearchConfig
        self._fa.research_config.bins = bins
        self._fa.research_config.rebalance_periods = rebalance_periods
        self._fa.research_config.return_horizons = return_horizons
        self._fa.research_config.fee_rate = fee_rate
        self._fa.research_config.slippage_rate = slippage_rate

    def run(self) -> "FactorBacktest":
        """執行回測（包括 IC 分析 + 分層回測）。"""
        self._fa.run()
        return self

    def ic_summary(self) -> dict:
        """回傳 IC 摘要：各 window 的 mean / std / IR。"""
        try:
            # FactorAnalyzer 內部儲存 ic_results 在 calc_single_fac_ic 之後
            ic_dict = getattr(self._fa, "_FactorAnalyzer__ic_results", None)
            if ic_dict is None:
                return {"error": "IC results not available. Call create_single_fac_ic_sheet() first."}

            summary = {}
            for window, ics in ic_dict.items():
                import statistics as st
                import math
                clean = [x for x in ics if not math.isnan(x)]
                if len(clean) < 2:
                    summary[str(window)] = {"mean": None, "std": None, "ir": None, "n": len(clean)}
                    continue
                mean = st.fmean(clean)
                std = st.pstdev(clean)
                summary[str(window)] = {
                    "mean": round(mean, 6),
                    "std": round(std, 6),
                    "ir": round(mean / std, 4) if std else None,
                    "n": len(clean),
                }
            return summary
        except Exception as e:
            return {"error": str(e)}

    def create_long_report(self) -> dict:
        """多頭分層回測摘要。"""
        # FactorAnalyzer HTML 報表儲存在內部路徑
        import tempfile, os
        tmp = tempfile.gettempdir()
        try:
            self._fa.create_long_return_sheet()
        except Exception as e:
            return {"error": str(e)}
        return {"status": "ok", "note": "Long-only quantile backtest completed"}

    def create_long_short_report(self) -> dict:
        """多空分層回測摘要。"""
        try:
            self._fa.create_long_short_return_sheet()
        except Exception as e:
            return {"error": str(e)}
        return {"status": "ok", "note": "Long-short quantile backtest completed"}

    def create_ic_report(self) -> dict:
        """IC 分析報表。"""
        try:
            self._fa.create_single_fac_ic_sheet()
        except Exception as e:
            return {"error": str(e)}
        return {"status": "ok", "note": "IC analysis report created"}

    def run_full_report(self) -> dict:
        """執行完整回測報告（多頭/多空/空頭 + IC）。"""
        results = {}
        for name, method in [
            ("long", self._fa.create_long_return_sheet),
            ("long_short", self._fa.create_long_short_return_sheet),
            ("short", self._fa.create_short_return_sheet),
            ("ic", self._fa.create_single_fac_ic_sheet),
        ]:
            try:
                method()
                results[name] = "ok"
            except Exception as e:
                results[name] = str(e)
        return results


def backtest_factor_from_config(
    df: pl.DataFrame,
    factor_name: str,
    config: Optional[dict] = None,
) -> FactorBacktest:
    """從 config.yaml 讀取參數建立 FactorBacktest。

    Args:
        df: Polars DataFrame
        factor_name: 因子名稱
        config: factor-lab 的 research 區段設定（可選，預設讀取 config.yaml）

    Returns:
        已初始化的 FactorBacktest
    """
    import yaml
    from pathlib import Path

    if config is None:
        config_path = Path(__file__).parent.parent / "config.yaml"
        if config_path.exists():
            with open(config_path) as f:
                full = yaml.safe_load(f)
                config = full.get("research", {})

    kwargs = {}
    if config:
        kwargs["return_horizons"] = (config.get("ic_horizon_days", 5),)

    return FactorBacktest(df, factor_name=factor_name, **kwargs)


# ═══════════════════════════════════════════════════════════════════════════════
# ADRS 防呆框架 (Anti-Data-Snooping Robustness Suite)
# 獨立 module-level 函數，不修改既有 FactorBacktest 類別
# ═══════════════════════════════════════════════════════════════════════════════

import random
import math
import statistics as _st


def compute_pbo(returns: list[float], n_trials: int = 1000) -> float:
    """López de Prado (2016) Probability of Backtest Overfitting (PBO).

    PBO > 0.5 → 回測很可能過擬合。

    演算法：
      T = len(returns); M = T // 2 (in-sample = 一半)
      每個 trial: 隨機選 M 個索引做 IS Sharpe，剩餘做 OOS Sharpe
      計算 OOS Sharpe < IS Sharpe 的頻率 → PBO

    Args:
        returns: 策略回報序列（list of float）
        n_trials: 隨機組合數（預設 1000）

    Returns:
        float: PBO 值，介於 0.0 ~ 1.0
    """
    T = len(returns)
    if T < 4:
        return 1.0  # 資料太少，視為過擬合

    M = T // 2  # in-sample size
    if M < 2:
        return 1.0

    indices = list(range(T))
    rng = random.Random(42)  # 固定種子以利重現

    def _sharpe(rs: list[float]) -> float:
        """計算年化 Sharpe ratio (假設日線資料)。"""
        clean = [x for x in rs if not math.isnan(x)]
        if len(clean) < 2:
            return -999.0
        mu = _st.fmean(clean)
        sd = _st.pstdev(clean)
        if sd == 0:
            return 0.0
        return (mu / sd) * math.sqrt(365)  # 年化

    oos_worse = 0
    for _ in range(n_trials):
        rng.shuffle(indices)
        is_idx = set(indices[:M])
        is_r = [returns[i] for i in is_idx]
        oos_r = [returns[i] for i in range(T) if i not in is_idx]
        is_sharpe = _sharpe(is_r)
        oos_sharpe = _sharpe(oos_r)
        if oos_sharpe < is_sharpe:
            oos_worse += 1

    return oos_worse / n_trials


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Acklam 反常態 CDF 近似（無 scipy 相依）。"""
    if p <= 0.0:
        return -1e10
    if p >= 1.0:
        return 1e10
    a = [-3.969683028665376e1, 2.209460984245205e2, -2.759285104469687e2,
         1.383577518672690e2, -3.066479806614716e1, 2.506628277459239e0]
    b = [-5.447609879822406e1, 1.615858368580409e2, -1.556989798598866e2,
         6.680131188771972e1, -1.328068155288572e1]
    c = [-7.784894002430293e-3, -3.223964580411365e-1, -2.400758277161838e0,
         -2.549732539343734e0, 4.374664141464968e0, 2.938163982698783e0]
    d = [7.784695709041462e-3, 3.224671290700398e-1, 2.445134137142996e0, 3.754408661907416e0]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)


def deflated_sharpe(returns, n_trials: int = 1, sr_trials_ann=None, ann: float | None = None) -> dict:
    """Deflated Sharpe Ratio（Bailey & López de Prado 2014）：在「試 N 組參數挑最好」之下，
    觀測 Sharpe 為真（>SR0）的機率，考慮偏度/峰度/樣本長度/試驗數。DSR≥0.95 才算可信。
    sr_trials_ann: 該網格各組的年化 Sharpe（用來估 SR0 的試驗離散度）。"""
    if ann is None:
        ann = _ANN
    r = [float(x) for x in returns if x == x]
    T = len(r)
    if T < 8:
        return {"dsr": None, "note": "樣本不足"}
    mu, sd = _st.fmean(r), _st.stdev(r)
    if sd == 0:
        return {"dsr": None, "note": "零波動"}
    sr = mu / sd  # per-period
    g3 = sum((x - mu) ** 3 for x in r) / T / sd ** 3
    g4 = sum((x - mu) ** 4 for x in r) / T / sd ** 4  # 標準化第四動差（非超額）
    gamma = 0.5772156649015329
    trials = [s / ann for s in (sr_trials_ann or []) if s == s]
    if len(trials) > 1:
        sd_sr, N = _st.pstdev(trials), len(trials)
    else:
        sd_sr, N = 0.0, max(1, n_trials)
    sr0 = (sd_sr * ((1 - gamma) * _norm_ppf(1 - 1.0 / N) + gamma * _norm_ppf(1 - 1.0 / (N * math.e)))
           if sd_sr > 0 and N > 1 else 0.0)
    denom = math.sqrt(max(1e-12, 1 - g3 * sr + ((g4 - 1) / 4.0) * sr * sr))
    z = (sr - sr0) * math.sqrt(T - 1) / denom
    return {"dsr": round(_norm_cdf(z), 3), "sr_ann": round(sr * ann, 3),
            "sr0_ann": round(sr0 * ann, 3), "n_trials": N,
            "skew": round(g3, 3), "kurtosis": round(g4, 3)}


def purged_cv_sharpe(
    signal: list[float],
    fwd_returns: list[float],
    n_splits: int = 5,
) -> dict:
    """Purged Cross-Validation：時間序列分割 + OLS 係數外推。

    每個 fold:
      Training set: 前 k 份資料，用 OLS (fwd_returns ~ signal) 擬合 coef
      Test set: 第 k+1 份資料，用 coef * signal 做多頭信號，計算 Sharpe

    Args:
        signal: 因子信號序列（list of float）
        fwd_returns: 未來報酬序列（list of float），與 signal 同長度
        n_splits: 分割數（預設 5）

    Returns:
        dict: {cv_sharpe_mean, cv_sharpe_std, cv_sharpe_individual, n_splits}
    """
    N = min(len(signal), len(fwd_returns))
    if N < n_splits + 2:
        return {
            "cv_sharpe_mean": 0.0,
            "cv_sharpe_std": 0.0,
            "cv_sharpe_individual": [],
            "n_splits": n_splits,
        }

    def _ols_slope(xs: list[float], ys: list[float]) -> float:
        """簡單 OLS: y ~ x (無截距項，方便信號縮放)。"""
        n = len(xs)
        if n < 2:
            return 0.0
        xy = sum(x * y for x, y in zip(xs, ys))
        xx = sum(x * x for x in xs)
        return xy / xx if xx != 0 else 0.0

    def _long_only_sharpe(sig: list[float], rets: list[float]) -> float:
        """只做多：信號 > 0 持有，否則空倉。年化 Sharpe。"""
        strat = []
        for s, r in zip(sig, rets):
            strat.append(r if s > 0 else 0.0)
        clean = [x for x in strat if not math.isnan(x)]
        if len(clean) < 2:
            return -999.0
        mu = _st.fmean(clean)
        sd = _st.pstdev(clean)
        if sd == 0:
            return 0.0
        return (mu / sd) * math.sqrt(365)

    fold_size = N // n_splits
    cv_sharpes = []

    for i in range(1, n_splits):
        split = i * fold_size
        train_sig = signal[:split]
        train_ret = fwd_returns[:split]
        test_sig = signal[split: split + fold_size]
        test_ret = fwd_returns[split: split + fold_size]

        if len(train_sig) < 2 or len(test_sig) < 2:
            continue

        coef = _ols_slope(train_sig, train_ret)
        scaled_sig = [s * coef for s in test_sig]
        sh = _long_only_sharpe(scaled_sig, test_ret)
        if not math.isnan(sh) and sh > -999:
            cv_sharpes.append(sh)

    if len(cv_sharpes) < 2:
        return {
            "cv_sharpe_mean": cv_sharpes[0] if cv_sharpes else 0.0,
            "cv_sharpe_std": 0.0,
            "cv_sharpe_individual": cv_sharpes,
            "n_splits": n_splits,
        }

    return {
        "cv_sharpe_mean": round(_st.fmean(cv_sharpes), 4),
        "cv_sharpe_std": round(_st.pstdev(cv_sharpes), 4),
        "cv_sharpe_individual": [round(s, 4) for s in cv_sharpes],
        "n_splits": n_splits,
    }


def walk_forward_sharpe(
    signal: list[float],
    fwd_returns: list[float],
    train_ratio: float = 0.67,
) -> dict:
    """Walk-Forward Analysis：前 train_ratio 訓練，後段測試。

    wf_decay = (IS Sharpe - OOS Sharpe) / IS Sharpe
    優良指標：wf_decay < 0.5（OOS Sharpe 不低於 IS Sharpe 的一半）

    Args:
        signal: 因子信號序列
        fwd_returns: 未來報酬序列
        train_ratio: 訓練集比例（預設 0.67）

    Returns:
        dict: {is_sharpe, oos_sharpe, wf_decay, train_n, test_n}
    """
    N = min(len(signal), len(fwd_returns))
    split = int(N * train_ratio)
    if split < 2 or N - split < 2:
        return {"is_sharpe": 0.0, "oos_sharpe": 0.0, "wf_decay": 1.0, "train_n": split, "test_n": N - split}

    def _long_only_sharpe(sig: list[float], rets: list[float]) -> float:
        strat = []
        for s, r in zip(sig, rets):
            strat.append(r if s > 0 else 0.0)
        clean = [x for x in strat if not math.isnan(x)]
        if len(clean) < 2:
            return 0.0
        mu = _st.fmean(clean)
        sd = _st.pstdev(clean)
        if sd == 0:
            return 0.0
        return (mu / sd) * math.sqrt(365)

    is_sig = signal[:split]
    is_ret = fwd_returns[:split]
    oos_sig = signal[split:]
    oos_ret = fwd_returns[split:]

    is_sharpe = _long_only_sharpe(is_sig, is_ret)
    oos_sharpe = _long_only_sharpe(oos_sig, oos_ret)

    wf_decay = (is_sharpe - oos_sharpe) / is_sharpe if is_sharpe != 0 else 1.0

    return {
        "is_sharpe": round(is_sharpe, 4),
        "oos_sharpe": round(oos_sharpe, 4),
        "wf_decay": round(wf_decay, 4),
        "train_n": split,
        "test_n": N - split,
    }


def sensitivity_check(
    df: "pl.DataFrame",
    factor_fn,
    param_ranges: dict,
    metric_fn=None,
    n_trials: int = 100,
) -> dict:
    """參數敏感度分析。

    對 factor_fn 的每個參數，從 base value 做 ±20% 擾動，
    計算 metric_fn（預設：long-only Sharpe ratio of forward returns）。
    穩定條件：metric_std / abs(metric_mean) < 0.30

    Args:
        df: Polars DataFrame，需含 close 欄位
        factor_fn: 因子計算函數，簽名 factor_fn(df, **kwargs) → list[float]
        param_ranges: 參數範圍 dict，格式 {param_name: {"base": value}}
                      base 為基準值，會自動 ±20% 取樣
        metric_fn: 評估函數，簽名 metric_fn(signal, fwd_returns) → float
                   預設使用 long-only Sharpe
        n_trials: 每個參數的擾動次數（預設 100）

    Returns:
        dict: {param_name: {base_value, perturbed_values, metric_std,
                            metric_mean, metric_range, stable}}
    """
    if metric_fn is None:
        def _default_metric(sig, fwd):
            strat = []
            for s, r in zip(sig, fwd):
                strat.append(r if s > 0 else 0.0)
            clean = [x for x in strat if not math.isnan(x)]
            if len(clean) < 2:
                return 0.0
            mu = _st.fmean(clean)
            sd = _st.pstdev(clean)
            if sd == 0:
                return 0.0
            return (mu / sd) * math.sqrt(365)
        metric_fn = _default_metric

    # 計算 forward returns（避免前視偏差：shift(-1)）
    closes = df["close"].to_list()
    fwd_returns = [closes[i + 1] / closes[i] - 1.0 for i in range(len(closes) - 1)]

    results = {}
    rng = random.Random(42)

    for param_name, config in param_ranges.items():
        base_val = config["base"]
        # ±20% 範圍
        low = base_val * 0.8
        high = base_val * 1.2

        # 對整數型參數取整
        is_int = isinstance(base_val, int)

        metrics = []
        for _ in range(n_trials):
            perturbed = low + rng.random() * (high - low)
            if is_int:
                perturbed = max(1, int(round(perturbed)))

            try:
                # 建立臨時參數 dict
                trial_params = dict(config)
                trial_params["base"] = perturbed
                # 呼叫 factor_fn
                sig = factor_fn(df, **{param_name: perturbed})
                # 截齊長度
                min_len = min(len(sig), len(fwd_returns))
                m = metric_fn(sig[:min_len], fwd_returns[:min_len])
                if not math.isnan(m):
                    metrics.append(m)
            except Exception:
                continue

        if len(metrics) < 2:
            results[param_name] = {
                "base_value": base_val,
                "perturbed_values": metrics,
                "metric_std": 0.0,
                "metric_mean": metrics[0] if metrics else 0.0,
                "metric_range": 0.0,
                "stable": False,
            }
            continue

        mu = _st.fmean(metrics)
        sd = _st.pstdev(metrics)
        stable = (sd / abs(mu)) < 0.30 if mu != 0 else False

        results[param_name] = {
            "base_value": base_val,
            "perturbed_values": [round(m, 4) for m in metrics[:10]] + ["..."] if len(metrics) > 10 else [round(m, 4) for m in metrics],
            "metric_std": round(sd, 4),
            "metric_mean": round(mu, 4),
            "metric_range": round(max(metrics) - min(metrics), 4),
            "stable": stable,
        }

    return results


# ════════════════════════════════════════════════════════════════════════════════
# Phase 2：成本感知評估 + 參數網格(plateau) + rolling walk-forward
# 時序/單資產，與 scripts/onchain_eval.py 同一套成本/lag/年化(√365)慣例。
# 部位 pos∈[-1,1]；對齊價格、shift(lag) 杜前視、扣換手成本。供 quick_research(Phase 3)/報告取用。
# ════════════════════════════════════════════════════════════════════════════════
import itertools as _it
from pathlib import Path as _Path

_ANN = math.sqrt(365)


def load_btc_price(pkl: str = "empirical_runs/btcusdt_1d_1500.pkl"):
    """載入 BTC 日線 close（date-indexed pd.Series）。給 evaluate_positions / 優化器用。"""
    import pandas as pd
    p = _Path(pkl)
    if not p.is_absolute():
        p = _Path(__file__).resolve().parent.parent / pkl
    b = pd.read_pickle(p)
    b["date"] = pd.to_datetime(b["timestamp"], unit="ms").dt.floor("D")
    return b.set_index("date")["close"].astype(float).sort_index()


def evaluate_positions(pos, px, *, cost_bps: float = 10.0, lag: int = 1) -> dict:
    """成本感知評估（鏡像 scripts/onchain_eval.py 的 metrics）。
    pos: 部位 Series∈[-1,1]；px: close Series。回傳 metrics（含 net_returns 序列）。"""
    import pandas as pd
    px = pd.Series(px).sort_index()
    fwd = px.shift(-1) / px - 1.0
    pos = pd.Series(pos).sort_index().reindex(px.index).ffill().shift(lag).fillna(0.0).clip(-1, 1)
    turn = pos.diff().abs().fillna(pos.abs())
    net = ((pos * fwd) - turn * cost_bps / 1e4).fillna(0.0).dropna()
    n = len(net)
    sd = float(net.std(ddof=1)) if n > 1 else 0.0
    if n < 2 or sd == 0.0:
        return {"net_sharpe": 0.0, "ann_return": 0.0, "max_drawdown": 0.0, "t_stat": 0.0,
                "turnover_per_day": float(turn.mean()), "exposure": 0.0, "n": n,
                "net_returns": net, "position": pos}
    eq = (1 + net).cumprod(); dd = eq / eq.cummax() - 1.0
    mu = float(net.mean())
    return {
        "net_sharpe": round(mu / sd * _ANN, 3),
        "ann_return": round(mu * 365, 4),
        "max_drawdown": round(float(dd.min()), 4),
        "t_stat": round(mu / (sd / math.sqrt(n)), 3),
        "turnover_per_day": round(float(turn.mean()), 4),
        "exposure": round(float((pos.abs() > 1e-9).mean()), 3),
        "n": n,
        "net_returns": net,
        "position": pos,
    }


def grid_optimize(make_pos, param_grid: dict, px, *, cost_bps: float = 10.0, lag: int = 1,
                  objective: str = "net_sharpe", tol: float = 0.10, min_green: float = 0.0) -> dict:
    """全網格掃描 → 最佳參數 + plateau。
    make_pos(**params)->部位 Series；param_grid={name:[values]}。
    plateau_score = 落在最佳 (1-tol) 內的網格比例（那片綠的密度）；
    positive_frac = objective>min_green 的網格比例；robust = best>0 且 plateau≥0.5。
    剛好 2 參數時附 heatmap（z[row=y][col=x]）。"""
    names = list(param_grid)
    combos = list(_it.product(*(param_grid[n] for n in names)))
    results = []
    for combo in combos:
        params = dict(zip(names, combo))
        try:
            m = evaluate_positions(make_pos(**params), px, cost_bps=cost_bps, lag=lag)
            score, mdd = float(m.get(objective, 0.0)), m.get("max_drawdown")
        except Exception:
            score, mdd = float("nan"), None
        results.append({"params": params, "score": score, "max_drawdown": mdd})
    valid = [r for r in results if r["score"] == r["score"]]
    if not valid:
        return {"best_params": None, "best_score": None, "n_combos": len(combos), "n_valid": 0,
                "plateau_score": 0.0, "positive_frac": 0.0, "robust": False,
                "objective": objective, "results": results}
    best = max(valid, key=lambda r: r["score"])
    bs = best["score"]
    positive_frac = sum(1 for r in valid if r["score"] > min_green) / len(valid)
    plateau = (sum(1 for r in valid if r["score"] >= bs * (1 - tol)) / len(valid)) if bs > 0 else 0.0
    out = {
        "best_params": best["params"], "best_score": round(bs, 3),
        "best_max_drawdown": best["max_drawdown"], "n_combos": len(combos), "n_valid": len(valid),
        "plateau_score": round(plateau, 3), "positive_frac": round(positive_frac, 3),
        "robust": bool(bs > 0 and plateau >= 0.5), "objective": objective, "tol": tol,
        "results": results,
    }
    if len(names) == 2:
        xs, ys = list(param_grid[names[0]]), list(param_grid[names[1]])
        z = {(r["params"][names[0]], r["params"][names[1]]): r["score"] for r in results}
        out["heatmap"] = {"x_name": names[0], "x": xs, "y_name": names[1], "y": ys,
                          "z": [[z.get((x, y)) for x in xs] for y in ys]}
    return out


def rolling_walk_forward(make_pos, param_grid: dict, px, *, train_days: int, test_days: int,
                         step_days: int | None = None, cost_bps: float = 10.0, lag: int = 1,
                         objective: str = "net_sharpe", tol: float = 0.10) -> dict:
    """錨定/滾動 walk-forward：每折在 train 窗 grid_optimize 選參，套到 test 窗(OOS)，
    串接所有 OOS 報酬 → CV Sharpe + 正向折數 + OOS 最大回撤。窗以日曆天計（日線資料）。"""
    import pandas as pd
    px = pd.Series(px).sort_index()
    step_days = step_days or test_days
    idx = px.index
    end = idx.max()
    folds, oos_parts = [], []
    t0 = idx.min()
    while True:
        tr_hi = t0 + pd.Timedelta(days=train_days)
        te_hi = tr_hi + pd.Timedelta(days=test_days)
        if te_hi > end + pd.Timedelta(days=1):
            break
        px_tr = px[(idx >= t0) & (idx < tr_hi)]
        te_idx = px[(idx >= tr_hi) & (idx < te_hi)].index
        if len(px_tr) < 30 or len(te_idx) < 10:
            t0 = t0 + pd.Timedelta(days=step_days); continue
        bp = grid_optimize(make_pos, param_grid, px_tr, cost_bps=cost_bps, lag=lag,
                           objective=objective, tol=tol)["best_params"]
        if bp is None:
            t0 = t0 + pd.Timedelta(days=step_days); continue
        net = evaluate_positions(make_pos(**bp), px, cost_bps=cost_bps, lag=lag)["net_returns"]
        oos = net[(net.index >= tr_hi) & (net.index < te_hi)]
        sd = float(oos.std(ddof=1)) if len(oos) > 1 else 0.0
        fold_sharpe = float(oos.mean() / sd * _ANN) if sd else 0.0
        folds.append({"test": f"{tr_hi.date()}..{te_hi.date()}", "best_params": bp,
                      "oos_sharpe": round(fold_sharpe, 3),
                      "oos_return": round(float((1 + oos).prod() - 1), 4), "n": len(oos)})
        oos_parts.append(oos)
        t0 = t0 + pd.Timedelta(days=step_days)
    if not oos_parts:
        return {"n_folds": 0, "cv_sharpe": 0.0, "positive_folds": 0, "folds": []}
    allret = pd.concat(oos_parts).sort_index()
    allret = allret[~allret.index.duplicated(keep="first")]
    sd = float(allret.std(ddof=1))
    cv_sharpe = float(allret.mean() / sd * _ANN) if sd else 0.0
    eq = (1 + allret).cumprod(); dd = eq / eq.cummax() - 1.0
    pos_folds = sum(1 for f in folds if f["oos_sharpe"] > 0)
    return {
        "n_folds": len(folds), "cv_sharpe": round(cv_sharpe, 3),
        "positive_folds": pos_folds, "positive_fold_frac": round(pos_folds / len(folds), 3),
        "oos_total_return": round(float((1 + allret).prod() - 1), 4),
        "oos_max_drawdown": round(float(dd.min()), 4), "oos_days": len(allret),
        "train_days": train_days, "test_days": test_days, "step_days": step_days, "folds": folds,
    }
