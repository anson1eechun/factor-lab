"""
三個候選因子的 Smoke Test

驗證項目：
1. 無 crash（正常執行不拋異常）
2. 輸出合理範圍（signal 非全 NaN、數值在合理範圍）
3. 無前視偏誤（每個時間點的計算只使用 <= t 的資料）
4. 處理缺失值（NaN、inf）
5. 輸出標準化

執行方式:
    cd /home/anson/factor-lab
    python3 -m pytest scripts/test_signals_smoke.py -v
    或
    python3 scripts/test_signals_smoke.py
"""

from __future__ import annotations
import sys
import os
import math
import numpy as np

# 確保 factor-lab 在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.signals.F1_Complexity_Gap_Regime import compute as f1_compute
from core.signals.F2_Liquidity_Consumption_Tilt import compute as f2_compute
from core.signals.F3_Volatility_Roughness_Filter import compute as f3_compute


# ── 輔助函數 ──────────────────────────────────────────────────────

def generate_ohlcv(n: int, seed: int = 42, *, regime: str = "random") -> list[dict]:
    """
    生成合成 OHLCV 資料。
    
    regime:
      - "random": 幾何布朗運動
      - "trend": 帶有趨勢
      - "mean_revert": 均值回歸 (Ornstein-Uhlenbeck)
      - "volatile": 高波動率
    """
    rng = np.random.default_rng(seed)
    
    # 日內時間戳
    base_ts = 1700000000000  # 毫秒
    interval = 300000  # 5 分鐘
    
    # 生成對數價格
    if regime == "trend":
        drift = 0.0002
        vol = 0.01
        log_returns = drift + vol * rng.standard_normal(n)
    elif regime == "mean_revert":
        # OU 過程: dx = -theta * x * dt + sigma * dW
        theta = 0.1
        sigma = 0.015
        log_returns = np.zeros(n)
        x = 0.0
        for i in range(n):
            x = x - theta * x + sigma * rng.standard_normal()
            log_returns[i] = x
    elif regime == "volatile":
        # GARCH-like: 波動率叢聚
        vol = np.zeros(n)
        vol[0] = 0.01
        log_returns = np.zeros(n)
        for i in range(n):
            if i > 0:
                vol[i] = np.sqrt(0.000001 + 0.1 * log_returns[i-1]**2 + 0.85 * vol[i-1]**2)
            log_returns[i] = vol[i] * rng.standard_normal()
    else:
        vol = 0.01
        log_returns = vol * rng.standard_normal(n)
    
    # 累積價格
    log_price = np.cumsum(log_returns)
    price = 50000 * np.exp(log_price)
    
    # 生成 OHLCV
    data = []
    for i in range(n):
        c = max(0.01, price[i])
        # 生成日內高低價
        daily_range = c * abs(log_returns[i]) * 2.0 if i > 0 else c * 0.005
        h = c + daily_range * rng.uniform(0.3, 1.0)
        l = c - daily_range * rng.uniform(0.3, 1.0)
        o = l + (h - l) * rng.uniform(0.2, 0.8)
        v = abs(log_returns[i]) * c * 100 + rng.uniform(1, 50) if i > 0 else 100
        
        # 確保價格合理
        h = max(h, o, c)
        l = max(0.01, min(l, o, c))
        
        data.append({
            "ts": base_ts + i * interval,
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "close": round(c, 2),
            "volume": round(v, 4),
        })
    
    return data


def generate_ohlcv_with_nan(n: int, seed: int = 42, nan_ratio: float = 0.05) -> list[dict]:
    """生成含缺失值的 OHLCV 資料。"""
    data = generate_ohlcv(n, seed, regime="random")
    rng = np.random.default_rng(seed + 1)
    
    for d in data:
        if rng.random() < nan_ratio:
            field = rng.choice(["open", "high", "low", "close", "volume"])
            d[field] = float("nan")
    
    return data


def check_no_crash(result: dict, name: str) -> list[str]:
    """檢查結果是否正常產生。"""
    errors = []
    if "signal" not in result:
        errors.append(f"{name}: 缺少 'signal' 欄位")
        return errors
    signal = result["signal"]
    if signal is None:
        errors.append(f"{name}: signal 為 None")
    elif not isinstance(signal, np.ndarray):
        errors.append(f"{name}: signal 不是 np.ndarray")
    return errors


def check_output_range(result: dict, name: str, n_expected: int) -> list[str]:
    """檢查輸出範圍是否合理。"""
    errors = []
    signal = result["signal"]
    
    if len(signal) != n_expected:
        errors.append(f"{name}: signal 長度 {len(signal)} != 預期 {n_expected}")
    
    # 檢查是否全部為 NaN
    if np.all(np.isnan(signal)):
        errors.append(f"{name}: signal 全部為 NaN")
    
    # 檢查是否有非 NaN 值
    valid_count = np.sum(~np.isnan(signal))
    if valid_count == 0:
        errors.append(f"{name}: 無有效 signal 值")
    
    # 檢查是否有 inf
    if np.any(np.isinf(signal)):
        errors.append(f"{name}: signal 包含 inf")
    
    return errors


def check_no_lookahead(compute_fn, name: str, n_total: int = 600) -> list[str]:
    """
    檢查無前視偏誤：分別以遞增的資料長度呼叫 compute，
    驗證較早時間點的 signal 值在不同資料長度下保持一致。
    """
    errors = []
    
    # 生成完整資料
    full_data = generate_ohlcv(n_total, seed=99, regime="trend")
    
    # 對不同長度進行計算
    prev_signals = None
    test_lengths = [300, 400, 500, n_total]
    
    for length in test_lengths:
        partial_data = full_data[:length]
        result = compute_fn(partial_data)
        signal = result["signal"]
        
        if prev_signals is not None:
            # 比較重疊部分的 signal 值（取到較短長度）
            overlap_len = min(len(prev_signals), len(signal))
            # 只比較非 NaN 的部分
            for i in range(overlap_len):
                prev_val = prev_signals[i]
                curr_val = signal[i]
                if not (np.isnan(prev_val) or np.isnan(curr_val)):
                    if not np.isclose(prev_val, curr_val, rtol=1e-10, atol=1e-10):
                        errors.append(
                            f"{name}: 前視偏誤！位置 {i} 在資料長度變化時 signal 不一致 "
                            f"({prev_val:.8f} vs {curr_val:.8f})"
                        )
                        # 只報告第一個錯誤
                        return errors
        
        prev_signals = signal
    
    return errors


def check_standardization(result: dict, name: str) -> list[str]:
    """檢查標準化後的輸出是否合理。"""
    errors = []
    signal = result["signal"]
    valid = signal[~np.isnan(signal)]
    
    if len(valid) < 10:
        errors.append(f"{name}: 有效值太少 ({len(valid)})，無法檢查標準化")
        return errors
    
    # z-score 標準化後應接近 mean=0, std=1
    mean = np.mean(valid)
    std = np.std(valid)
    
    # 寬鬆檢查（因子可能不對稱）
    if abs(mean) > 0.5:
        errors.append(f"{name}: 標準化後均值偏離 ({mean:.4f})，預期接近 0")
    
    # 檢查範圍合理性（不應有極端值）
    max_abs = np.max(np.abs(valid))
    if max_abs > 5.0:
        errors.append(f"{name}: 標準化後極端值過大 ({max_abs:.4f})")
    
    return errors


# ── 各因子專屬測試 ────────────────────────────────────────────────

def test_f1_basic():
    """F1 基礎測試：無 crash、輸出合理"""
    print("\n═══ F1: Complexity Gap Regime ═══")
    errors = []
    
    # 正常資料測試
    n = 500
    data = generate_ohlcv(n, seed=1, regime="trend")
    result = f1_compute(data)
    errors.extend(check_no_crash(result, "F1"))
    errors.extend(check_output_range(result, "F1", n))
    errors.extend(check_standardization(result, "F1"))
    
    # 檢查 delta 範圍
    delta = result.get("delta")
    if delta is not None:
        valid_delta = delta[~np.isnan(delta)]
        if len(valid_delta) > 0:
            d_min, d_max = np.min(valid_delta), np.max(valid_delta)
            print(f"  Δ 範圍: [{d_min:.6f}, {d_max:.6f}]")
            # 相位分佈
            regime = result.get("regime")
            if regime is not None:
                for r in ["disordered", "critical", "ordered", "unknown"]:
                    cnt = np.sum(regime == r)
                    print(f"  {r}: {cnt}")
    
    # 多種市場狀態測試
    for reg in ["random", "mean_revert", "volatile"]:
        data_r = generate_ohlcv(n, seed=2, regime=reg)
        result_r = f1_compute(data_r)
        errors_r = check_no_crash(result_r, f"F1 ({reg})")
        if errors_r:
            errors.extend(errors_r)
        else:
            valid = result_r["signal"][~np.isnan(result_r["signal"])]
            if len(valid) > 0:
                print(f"  F1 ({reg}): signal mean={np.mean(valid):.4f}, std={np.std(valid):.4f}")
    
    # NaN 資料測試
    data_nan = generate_ohlcv_with_nan(n, seed=3, nan_ratio=0.1)
    result_nan = f1_compute(data_nan)
    errors.extend(check_no_crash(result_nan, "F1 (含 NaN)"))
    errors.extend(check_output_range(result_nan, "F1 (含 NaN)", n))
    
    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
    else:
        print(f"  PASS: 所有 F1 測試通過 ✓")
    
    return len(errors) == 0


def test_f1_no_lookahead():
    """F1 前視偏誤測試"""
    print("\n═══ F1: 前視偏誤檢查 ═══")
    errors = check_no_lookahead(
        lambda d: f1_compute(d, window=60, n_components=10),
        "F1"
    )
    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
    else:
        print(f"  PASS: F1 無前視偏誤 ✓")
    return len(errors) == 0


def test_f2_basic():
    """F2 基礎測試"""
    print("\n═══ F2: Liquidity Consumption Tilt ═══")
    errors = []
    
    n = 500
    data = generate_ohlcv(n, seed=10, regime="trend")
    result = f2_compute(data)
    errors.extend(check_no_crash(result, "F2"))
    errors.extend(check_output_range(result, "F2", n))
    errors.extend(check_standardization(result, "F2"))
    
    # 檢查 LCT 信號分佈
    raw_lct = result.get("raw_lct")
    if raw_lct is not None:
        valid_lct = raw_lct[~np.isnan(raw_lct)]
        if len(valid_lct) > 0:
            print(f"  raw LCT 範圍: [{np.min(valid_lct):.6f}, {np.max(valid_lct):.6f}]")
            print(f"  raw LCT mean: {np.mean(valid_lct):.6f}")
    
    # NaN 資料測試
    data_nan = generate_ohlcv_with_nan(n, seed=11, nan_ratio=0.1)
    result_nan = f2_compute(data_nan)
    errors.extend(check_no_crash(result_nan, "F2 (含 NaN)"))
    errors.extend(check_output_range(result_nan, "F2 (含 NaN)", n))
    
    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
    else:
        print(f"  PASS: 所有 F2 測試通過 ✓")
    
    return len(errors) == 0


def test_f2_no_lookahead():
    """F2 前視偏誤測試"""
    print("\n═══ F2: 前視偏誤檢查 ═══")
    errors = check_no_lookahead(
        lambda d: f2_compute(d),
        "F2"
    )
    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
    else:
        print(f"  PASS: F2 無前視偏誤 ✓")
    return len(errors) == 0


def test_f3_basic():
    """F3 基礎測試"""
    print("\n═══ F3: Volatility Roughness Filter ═══")
    errors = []
    
    n = 500
    for reg in ["random", "trend", "mean_revert", "volatile"]:
        data = generate_ohlcv(n, seed=20, regime=reg)
        result = f3_compute(data, window=100, dfa_min_window=60)
        
        # 使用不同的測試標籤
        label = f"F3 ({reg})"
        err = []
        err.extend(check_no_crash(result, label))
        err.extend(check_output_range(result, label, n))
        
        if err:
            errors.extend(err)
            continue
        
        # 檢查 Hurst 指數範圍
        hurst = result.get("hurst")
        if hurst is not None:
            valid_h = hurst[~np.isnan(hurst)]
            if len(valid_h) > 0:
                h_mean = np.mean(valid_h)
                h_std = np.std(valid_h)
                print(f"  {reg}: Hurst mean={h_mean:.4f}, std={h_std:.4f}, n_valid={len(valid_h)}")
                
                # Hurst 應在 [0, 1] 範圍
                if np.min(valid_h) < -0.01 or np.max(valid_h) > 1.01:
                    errors.append(f"{label}: Hurst 超出 [0,1] 範圍")
        
        # 檢查 multiplier 範圍
        mult = result.get("multiplier")
        if mult is not None:
            valid_m = mult[~np.isnan(mult)]
            if len(valid_m) > 0:
                m_min, m_max = np.min(valid_m), np.max(valid_m)
                print(f"  {reg}: multiplier 範圍 [{m_min:.2f}, {m_max:.2f}]")
                if m_min < 0.1 or m_max > 1.5:
                    errors.append(f"{label}: multiplier 範圍異常")
    
    # NaN 資料測試
    data_nan = generate_ohlcv_with_nan(n, seed=21, nan_ratio=0.1)
    result_nan = f3_compute(data_nan, window=100, dfa_min_window=60)
    errors.extend(check_no_crash(result_nan, "F3 (含 NaN)"))
    errors.extend(check_output_range(result_nan, "F3 (含 NaN)", n))
    
    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
    else:
        print(f"  PASS: 所有 F3 測試通過 ✓")
    
    return len(errors) == 0


def test_f3_no_lookahead():
    """F3 前視偏誤測試"""
    print("\n═══ F3: 前視偏誤檢查 ═══")
    errors = check_no_lookahead(
        lambda d: f3_compute(d, window=100, dfa_min_window=60),
        "F3"
    )
    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
    else:
        print(f"  PASS: F3 無前視偏誤 ✓")
    return len(errors) == 0


# ── 邊界條件測試 ──────────────────────────────────────────────────

def test_edge_cases():
    """邊界條件測試：極短資料、零成交量、固定價格"""
    print("\n═══ 邊界條件測試 ═══")
    errors = []
    
    # 極短資料
    tiny_data = generate_ohlcv(5, seed=30)
    
    for name, fn in [
        ("F1", lambda d: f1_compute(d, window=60, n_components=5)),
        ("F2", f2_compute),
        ("F3", lambda d: f3_compute(d, window=100, dfa_min_window=60)),
    ]:
        try:
            result = fn(tiny_data)
            signal = result["signal"]
            # 資料不足以計算時，應全部為 NaN（不 crash）
            if not isinstance(signal, np.ndarray):
                errors.append(f"{name} edge: signal 類型錯誤")
            print(f"  {name} (n=5): signal length={len(signal)}, all_nan={np.all(np.isnan(signal))}")
        except Exception as e:
            errors.append(f"{name} edge: 意外異常: {e}")
    
    # 固定價格（無波動率）
    n = 200
    flat_data = []
    for i in range(n):
        flat_data.append({
            "ts": 1700000000000 + i * 300000,
            "open": 50000.0,
            "high": 50000.01,
            "low": 49999.99,
            "close": 50000.0,
            "volume": 100.0,
        })
    
    for name, fn in [
        ("F1", lambda d: f1_compute(d, window=60, n_components=5)),
        ("F2", f2_compute),
        ("F3", lambda d: f3_compute(d, window=100, dfa_min_window=60)),
    ]:
        try:
            result = fn(flat_data)
            signal = result["signal"]
            print(f"  {name} (n={n}, flat): signal length={len(signal)}, "
                  f"all_nan={np.all(np.isnan(signal))}, "
                  f"has_inf={np.any(np.isinf(signal))}")
            if np.any(np.isinf(signal)):
                errors.append(f"{name} flat: signal 包含 inf")
        except Exception as e:
            errors.append(f"{name} flat: 意外異常: {e}")
    
    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
    else:
        print(f"  PASS: 邊界條件測試通過 ✓")
    
    return len(errors) == 0


def test_real_data_shape():
    """使用真實資料形狀測試（透過 CryptoAdapter 或模擬）"""
    print("\n═══ 真實資料形狀測試 ═══")
    
    try:
        from core.adapters.crypto import CryptoAdapter
        adapter = CryptoAdapter()
        data = adapter.ohlcv("BTC/USDT", timeframe="1h")
        n = len(data)
        print(f"  取得 {n} 筆 BTC/USDT 1h 真實 OHLCV 資料")
        
        if n >= 100:
            for name, fn, kwargs in [
                ("F1", f1_compute, {}),
                ("F2", f2_compute, {}),
                ("F3", f3_compute, {"window": 100, "dfa_min_window": 60}),
            ]:
                try:
                    result = fn(data, **kwargs)
                    signal = result["signal"]
                    valid = np.sum(~np.isnan(signal))
                    mean_s = np.nanmean(signal) if valid > 0 else float("nan")
                    print(f"  {name}: signal[n={len(signal)}, valid={valid}, mean={mean_s:.4f}]")
                except Exception as e:
                    print(f"  {name}: 異常: {e}")
        else:
            print(f"  資料不足 (n={n} < 100)，跳過真實資料測試")
        return True
    except ImportError as e:
        print(f"  CryptoAdapter 不可用: {e}")
        return True
    except Exception as e:
        print(f"  真實資料測試跳過: {e}")
        return True


# ── 主測試入口 ────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("  因子信號函數 Smoke Test")
    print("  F1: Complexity Gap Regime | F2: Liquidity Consumption Tilt")
    print("  F3: Volatility Roughness Filter")
    print("=" * 70)
    
    results = {}
    
    # F1
    results["F1_basic"] = test_f1_basic()
    results["F1_lookahead"] = test_f1_no_lookahead()
    
    # F2
    results["F2_basic"] = test_f2_basic()
    results["F2_lookahead"] = test_f2_no_lookahead()
    
    # F3
    results["F3_basic"] = test_f3_basic()
    results["F3_lookahead"] = test_f3_no_lookahead()
    
    # 邊界條件
    results["edge_cases"] = test_edge_cases()
    
    # 真實資料（可選）
    results["real_data"] = test_real_data_shape()
    
    # ── 總結 ──
    print("\n" + "=" * 70)
    print("  測試總結")
    print("=" * 70)
    
    all_pass = True
    for name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            all_pass = False
    
    print("=" * 70)
    if all_pass:
        print("  所有測試通過！")
    else:
        print("  部分測試失敗，請檢查上述輸出。")
    print("=" * 70)
    
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
