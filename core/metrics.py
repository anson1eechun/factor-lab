"""因子評估指標：Rank-IC / IC-IR。純標準庫實作（無 numpy）。

實證者(Empiricist agent) 用這些函數量化一個因子的預測力。
"""
from __future__ import annotations
import math, statistics as st


def _rank(xs: list[float]) -> list[float]:
    """平均排名（處理並列）。"""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson(a: list[float], b: list[float]) -> float:
    if len(a) < 3:
        return float("nan")
    ma, mb = st.fmean(a), st.fmean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db) if da and db else float("nan")


def rank_ic(factor_vals: list[float], fwd_returns: list[float]) -> float:
    """單一橫斷面的 Rank-IC = Spearman(因子值, 未來報酬)。"""
    return _pearson(_rank(factor_vals), _rank(fwd_returns))


def ic_series_stats(ics: list[float]) -> dict:
    """多期 IC 序列 → 均值、標準差、IC-IR。"""
    clean = [x for x in ics if not math.isnan(x)]
    if len(clean) < 2:
        return {"ic_mean": float("nan"), "ic_std": float("nan"), "ic_ir": float("nan"), "n": len(clean)}
    mean, sd = st.fmean(clean), st.pstdev(clean)
    return {"ic_mean": mean, "ic_std": sd,
            "ic_ir": mean / sd if sd else float("nan"), "n": len(clean)}


def forward_returns(closes: list[float], horizon: int) -> list[float]:
    """每個時點的未來 horizon 期報酬（最後 horizon 期為 None 去除）。"""
    out = []
    for i in range(len(closes) - horizon):
        out.append(closes[i + horizon] / closes[i] - 1.0)
    return out
