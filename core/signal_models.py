"""core.signal_models — Phase 1：signal-model 庫 + 依資料結構自動選模。

把「一條因子序列」轉成「部位序列 ∈[-1,1]」。每個 model 是純函數，比照既有 signal 風格
（rolling 標準化 → tanh 壓縮 → fillna(0)），不造框架。

方向與形狀解耦：model 決定「怎麼把資料異動變成曝險」，direction(±1) 決定「站哪一邊」（由
alpha story 決定）。對齊影片：依資料結構（連續 / 有號流量 / 偏態 / 尖峰 / 趨勢）自動匹配模型。

用法（research 端，uv run --with pandas --with numpy）：
    from core.data import load
    from core.signal_models import auto_signal, data_profile
    s = load("coinbase_premium_gap")
    prof = data_profile(s)              # {tags, recommended_model, reason, 統計...}
    pos = auto_signal(s, direction=1)   # -> pd.Series 部位，可直接餵 scripts/onchain_eval.py
契約見 docs/SIGNAL_CONTRACT.md。
"""
from __future__ import annotations
import numpy as np
import pandas as pd


# ── 共用工具 ────────────────────────────────────────────────
def _z(s: pd.Series, w: int = 30) -> pd.Series:
    sd = s.rolling(w).std()
    return (s - s.rolling(w).mean()) / sd.replace(0.0, np.nan)


def _finish(pos: pd.Series, direction: int) -> pd.Series:
    return (direction * pos).fillna(0.0).clip(-1.0, 1.0)


# ── 5 個 signal model：series -> position ∈[-1,1] ───────────
def zscore_reversion(s: pd.Series, w: int = 30, direction: int = 1) -> pd.Series:
    """連續、近對稱、均值回歸序列：fade 極值（高→空、低→多）。MFI 超賣→買即此。"""
    return _finish(-np.tanh(_z(s, w)), direction)


def trend_drift(s: pd.Series, w: int = 120, direction: int = 1) -> pd.Series:
    """持續/趨勢序列：順著相對長期均值的漂移（高於長均→多）。"""
    sd = s.rolling(w).std().replace(0.0, np.nan)
    return _finish(np.tanh((s - s.rolling(w).mean()) / sd), direction)


def percentile_rank(s: pd.Series, w: int = 120, direction: int = 1) -> pd.Series:
    """非常態/偏態/有界序列：滾動分位數（對離群穩健），高分位→多。"""
    r = s.rolling(w).apply(lambda x: float((x <= x[-1]).mean()), raw=True)
    return _finish(2.0 * r - 1.0, direction)


def breakout_spike(s: pd.Series, w: int = 30, k: float = 2.0, hold: int = 3,
                   direction: int = 1) -> pd.Series:
    """尖峰/突跳序列：z 超過 ±k 觸發、持有 hold 根（事件式，非連續曝險）。"""
    z = _z(s, w)
    raw = pd.Series(np.nan, index=s.index)
    raw[z > k] = 1.0
    raw[z < -k] = -1.0
    return _finish(raw.ffill(limit=hold), direction)


def sign_flow(s: pd.Series, w: int = 30, direction: int = 1) -> pd.Series:
    """繞零的有號流量（netflow 類）：以滾動尺度標準化的符號為主（正流→正部位）。"""
    scale = s.abs().rolling(w).mean().replace(0.0, np.nan)
    return _finish(np.tanh(s / scale), direction)


MODELS = {
    "zscore_reversion": zscore_reversion,
    "trend_drift": trend_drift,
    "percentile_rank": percentile_rank,
    "breakout_spike": breakout_spike,
    "sign_flow": sign_flow,
}


# ── 資料結構分析 → 建議 model ──────────────────────────────
def _skew(a: np.ndarray) -> float:
    a = a - a.mean(); sd = a.std()
    return float((a ** 3).mean() / sd ** 3) if sd else 0.0


def _excess_kurt(a: np.ndarray) -> float:
    a = a - a.mean(); sd = a.std()
    return float((a ** 4).mean() / sd ** 4 - 3.0) if sd else 0.0


def _ac(x, lag: int = 1) -> float:
    r = pd.Series(x).autocorr(lag)
    return float(r) if pd.notna(r) else 0.0


def data_profile(s: pd.Series) -> dict:
    """分析序列的資料結構 → 統計 + tag + 建議 model + 理由（透明、非黑箱）。"""
    a = pd.Series(s).dropna().astype(float).values
    n = len(a)
    if n < 30:
        return {"n": n, "tags": ["too_short"], "recommended_model": "zscore_reversion",
                "reason": "樣本太少，預設均值回歸"}
    mean = float(a.mean())
    std = float(a.std(ddof=1)) or 1e-12
    sk, ku = _skew(a), _excess_kurt(a)
    has_neg = bool((a < 0).any())
    all_pos = bool((a > 0).all())
    centered = abs(mean) / std
    sign_change_rate = float((np.diff(np.sign(a)) != 0).mean())
    ac1, ac1_diff = _ac(a, 1), _ac(np.diff(a), 1)

    if has_neg and centered < 0.5 and sign_change_rate > 0.12:
        tag, model, reason = "signed", "sign_flow", \
            f"繞零有號流量（|mean|/std={centered:.2f}, 變號率={sign_change_rate:.2f}）"
    elif ku > 8.0:
        tag, model, reason = "spiky", "breakout_spike", f"厚尾尖峰（excess kurtosis={ku:.1f}）"
    elif abs(sk) > 1.5 or (all_pos and sk > 1.0):
        tag, model, reason = "skewed", "percentile_rank", f"偏態（skew={sk:.2f}）→ 分位數較穩健"
    elif ac1 > 0.97 and ac1_diff > 0.0:
        tag, model, reason = "trending", "trend_drift", \
            f"高持續趨勢（ac1={ac1:.3f}, Δac1={ac1_diff:.2f}）"
    else:
        tag, model, reason = "continuous", "zscore_reversion", "近對稱連續 → 預設均值回歸"

    return {"n": n, "mean": round(mean, 4), "std": round(std, 4), "skew": round(sk, 3),
            "excess_kurtosis": round(ku, 2), "has_negative": has_neg,
            "centered": round(centered, 3), "sign_change_rate": round(sign_change_rate, 3),
            "autocorr1": round(ac1, 3), "autocorr1_diff": round(ac1_diff, 3),
            "tags": [tag], "recommended_model": model, "reason": reason}


def auto_signal(s: pd.Series, direction: int = 1, model: str | None = None, **params) -> pd.Series:
    """依 data_profile 自動選 model（或用 model= 指定），回傳部位 Series ∈[-1,1]。
    direction(±1) 由 alpha story 決定。要看選模理由請另呼叫 data_profile(s)。"""
    name = model or data_profile(s)["recommended_model"]
    if name not in MODELS:
        raise ValueError(f"未知 model {name!r}；可用：{list(MODELS)}")
    return MODELS[name](s, direction=direction, **params)


# ── regime 條件化 與 factor 組合（combinations / regime-conditioning）──
def regime_masks(px: pd.Series) -> dict:
    """從 BTC 價格算**因果(無前視)** regime 遮罩：趨勢(100d SMA 上/下)、波動(30d 實現波動 vs 擴張中位數)。
    回 {name: bool Series}；歷史不足處為 False(空手)。遮罩用到 t 為止的資料，部位仍由 harness 再 lag。"""
    px = pd.Series(px).sort_index()
    ret = px.pct_change()
    sma = px.rolling(100).mean()
    vol = ret.rolling(30).std()
    vmed = vol.expanding(min_periods=60).median()
    return {
        "trend_up": (px > sma).fillna(False),
        "trend_down": (px < sma).fillna(False),
        "vol_high": (vol > vmed).fillna(False),
        "vol_low": (vol <= vmed).fillna(False),
    }


def condition_on_regime(pos: pd.Series, mask: pd.Series) -> pd.Series:
    """只在 regime 內持倉，regime 外歸零(空手)。"""
    m = pd.Series(mask).reindex(pos.index).fillna(False).astype(bool)
    return pos.where(m, 0.0)


def composite(positions: list) -> pd.Series:
    """等權合成多個部位(各自已含方向) → 平均(略過缺值)後 clip 到 [-1,1]。"""
    df = pd.concat([pd.Series(p) for p in positions], axis=1)
    return df.mean(axis=1).clip(-1.0, 1.0)
