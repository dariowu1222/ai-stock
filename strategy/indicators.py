import numpy as np
import pandas as pd


def _copy_sorted(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    if "date" in result.columns:
        result = result.sort_values("date").reset_index(drop=True)
    return result


def add_moving_averages(df: pd.DataFrame, windows: list[int] = [5, 10, 20, 60]) -> pd.DataFrame:
    result = _copy_sorted(df)
    for window in windows:
        result[f"ma{window}"] = result["close"].rolling(window=window).mean()
    return result


def add_volume_averages(df: pd.DataFrame, windows: list[int] = [5, 20]) -> pd.DataFrame:
    result = _copy_sorted(df)
    for window in windows:
        result[f"avg_volume_{window}"] = result["volume"].rolling(window=window).mean()
    return result


def add_rsi(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    result = _copy_sorted(df)
    delta = result["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=window).mean()
    avg_loss = loss.rolling(window=window).mean()
    rs = avg_gain / avg_loss
    result[f"rsi{window}"] = 100 - (100 / (1 + rs))
    result.loc[(avg_loss == 0) & (avg_gain > 0), f"rsi{window}"] = 100
    return result


def add_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    result = _copy_sorted(df)
    ema_fast = result["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = result["close"].ewm(span=slow, adjust=False).mean()
    result["macd"] = ema_fast - ema_slow
    result["macd_signal"] = result["macd"].ewm(span=signal, adjust=False).mean()
    result["macd_hist"] = result["macd"] - result["macd_signal"]
    return result


def add_kd(df: pd.DataFrame, window: int = 9) -> pd.DataFrame:
    result = _copy_sorted(df)
    low_min = result["low"].rolling(window=window).min()
    high_max = result["high"].rolling(window=window).max()
    denominator = (high_max - low_min).replace(0, np.nan)
    result["rsv"] = (result["close"] - low_min) / denominator * 100
    result["k"] = result["rsv"].ewm(alpha=1 / 3, adjust=False).mean()
    result["d"] = result["k"].ewm(alpha=1 / 3, adjust=False).mean()
    return result


def add_high_low_breakout(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    result = _copy_sorted(df)
    result[f"high_{window}"] = result["high"].shift(1).rolling(window=window).max()
    result[f"low_{window}"] = result["low"].shift(1).rolling(window=window).min()
    return result


def add_atr(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    result = _copy_sorted(df)
    previous_close = result["close"].shift(1)
    true_range = pd.concat(
        [
            result["high"] - result["low"],
            (result["high"] - previous_close).abs(),
            (result["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    result[f"atr{window}"] = true_range.rolling(window=window).mean()
    return result


def add_return_features(df: pd.DataFrame) -> pd.DataFrame:
    result = _copy_sorted(df)
    result["daily_return"] = result["close"].pct_change()
    return result


def add_bias(df: pd.DataFrame, ma_col: str = "ma20") -> pd.DataFrame:
    result = _copy_sorted(df)
    if ma_col not in result.columns:
        result = add_moving_averages(result, [20])
    result["bias"] = (result["close"] - result[ma_col]) / result[ma_col]
    return result


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    result = _copy_sorted(df)
    result = add_moving_averages(result)
    result = add_volume_averages(result)
    result = add_rsi(result)
    result = add_macd(result)
    result = add_kd(result)
    result = add_high_low_breakout(result)
    result = add_atr(result)
    result = add_return_features(result)
    result = add_bias(result)
    return result
