"""因子曝險與收益歸因：包裝 AlphaPurify.Exposures，為 Pipeline B Arbiter
提供因子獨立性判斷和邊際貢獻分析。

用法：
    from core.exposures import analyze_exposures
    result = analyze_exposures(df, factor_name="alpha_003",
                               exposure_cols=["momentum_12_1", "vol_60", "beta_252"])
"""

from __future__ import annotations
from typing import Optional
import polars as pl
from alphapurify import PureExposures


def analyze_exposures(
    df: pl.DataFrame,
    *,
    factor_name: str,
    exposure_cols: list[str],
    trade_date_col: str = "datetime",
    symbol_col: str = "symbol",
    price_col: str = "close",
) -> dict:
    """執行純因子曝險與收益歸因分析。

    將目標因子的收益分解為：
      1. 其他因子曝險的系統性貢獻
      2. 殘差 Alpha（因子獨特貢獻）

    Args:
        df: Polars DataFrame，需含所有 exposure_cols + factor_name
        factor_name: 目標因子名稱
        exposure_cols: 控制變數（其他因子）
        trade_date_col: 時間欄位
        symbol_col: 資產欄位
        price_col: 價格欄位

    Returns:
        dict with keys: status, message
    """
    if not exposure_cols:
        return {"status": "error", "message": "exposure_cols cannot be empty"}

    # 檢查必要欄位
    required = {trade_date_col, symbol_col, price_col, factor_name} | set(exposure_cols)
    missing = required - set(df.columns)
    if missing:
        return {"status": "error", "message": f"Missing columns: {missing}"}

    try:
        ex = PureExposures(
            base_df=df,
            trade_date_col=trade_date_col,
            symbol_col=symbol_col,
            price_col=price_col,
            factor_name=factor_name,
            exposure_cols=exposure_cols,
        )
        ex.run()
        return {
            "status": "ok",
            "message": f"Exposure analysis for '{factor_name}' vs {exposure_cols} completed",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def factor_correlation_matrix(
    df: pl.DataFrame,
    factor_cols: list[str],
    date_col: str = "datetime",
) -> dict:
    """計算因子間的相關性矩陣（跨時間平均）。

    用於 Arbiter 判斷新因子是否與既有因子高度重疊。

    Args:
        df: Polars DataFrame
        factor_cols: 因子欄位列表
        date_col: 日期欄位

    Returns:
        {"correlations": {f1: {f2: corr}}, "avg_abs_corr": float}
    """
    import statistics as st

    if len(factor_cols) < 2:
        return {"correlations": {}, "avg_abs_corr": 0.0}

    corr_matrix = {f1: {} for f1 in factor_cols}
    all_abs_corrs = []

    for i, f1 in enumerate(factor_cols):
        for j, f2 in enumerate(factor_cols):
            if i == j:
                corr_matrix[f1][f2] = 1.0
                continue
            # 計算 f1, f2 的 Pearson correlation（pooled cross-section）
            valid = df.select([f1, f2]).drop_nulls()
            if len(valid) < 3:
                corr_matrix[f1][f2] = None
                continue
            a = valid[f1].to_list()
            b = valid[f2].to_list()
            ma, mb = st.fmean(a), st.fmean(b)
            num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
            da = (sum((x - ma) ** 2 for x in a)) ** 0.5
            db = (sum((y - mb) ** 2 for y in b)) ** 0.5
            corr = num / (da * db) if da and db else None
            corr_matrix[f1][f2] = round(corr, 4) if corr is not None else None
            if corr is not None:
                all_abs_corrs.append(abs(corr))

    avg_abs = st.fmean(all_abs_corrs) if all_abs_corrs else 0.0
    return {
        "correlations": corr_matrix,
        "avg_abs_corr": round(avg_abs, 4),
    }
