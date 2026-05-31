"""因子預處理層：包裝 AlphaPurify.AlphaPurifier，為 factor-lab Pipeline B 提供
去極值、中性化、標準化等 40+ 清洗方法。

用法：
    from core.preprocessing import preprocess_factor
    df_clean = preprocess_factor(df, factor_col="momentum_20",
                                 winsorize="mad", standardize="zscore")
"""

from __future__ import annotations
from typing import Optional
import polars as pl
from alphapurify import AlphaPurifier


# ── 支援的方法常數 ──────────────────────────────────────────────
WINSORIZE_METHODS = {
    "mad", "sigma", "percentile", "quantile", "boxplot",
}

NEUTRALIZE_METHODS = {
    "market_cap", "sector", "industry", "ols", "ridge", "lasso",
    "pca", "elastic_net", "robust",
}

STANDARDIZE_METHODS = {
    "zscore", "minmax", "rank", "robust", "mad",
}


def preprocess_factor(
    df: pl.DataFrame,
    factor_col: str,
    *,
    winsorize: Optional[str] = None,
    winsorize_kwargs: Optional[dict] = None,
    neutralize: Optional[str] = None,
    neutralize_kwargs: Optional[dict] = None,
    standardize: Optional[str] = None,
    standardize_kwargs: Optional[dict] = None,
) -> pl.DataFrame:
    """鏈式因子清洗 Pipeline。

    Args:
        df: Polars DataFrame，需含 factor_col
        factor_col: 要清洗的因子欄位名稱
        winsorize: 去極值方法 (mad/sigma/percentile/quantile/boxplot)
        neutralize: 中性化方法 (ols/ridge/lasso/pca/market_cap/sector/industry/elastic_net/robust)
        standardize: 標準化方法 (zscore/minmax/rank/robust/mad)

    Returns:
        清洗後的 DataFrame（新增欄位 {factor_col}_clean）
    """
    kwargs = {}
    if winsorize_kwargs:
        kwargs.update(winsorize_kwargs)
    if neutralize_kwargs:
        kwargs.update(neutralize_kwargs)
    if standardize_kwargs:
        kwargs.update(standardize_kwargs)

    purifier = AlphaPurifier(df, factor_col=factor_col, **kwargs)

    if winsorize:
        purifier = purifier.winsorize(method=winsorize)
    if neutralize:
        purifier = purifier.neutralize(method=neutralize)
    if standardize:
        purifier = purifier.standardize(method=standardize)

    return purifier.to_result()


def batch_preprocess(
    df: pl.DataFrame,
    factor_cols: list[str],
    **kwargs,
) -> pl.DataFrame:
    """批次處理多個因子欄位。

    Args:
        df: Polars DataFrame
        factor_cols: 因子欄位列表
        **kwargs: 傳給 preprocess_factor 的參數

    Returns:
        含所有 {col}_clean 欄位的 DataFrame
    """
    result = df
    for col in factor_cols:
        result = preprocess_factor(result, factor_col=col, **kwargs)
    return result
