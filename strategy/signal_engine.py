import pandas as pd

from strategy.indicators import add_all_indicators
from strategy.templates import get_strategy_template


def _with_default_params(strategy_name: str, params: dict | None) -> dict:
    template = get_strategy_template(strategy_name)
    merged = dict(template.get("default_params", {}))
    merged.update(params or {})
    return merged


def _ensure_indicators(df: pd.DataFrame) -> pd.DataFrame:
    required = {"ma5", "ma20", "ma60", "avg_volume_20", "rsi14", "macd_hist", "high_20"}
    if required.issubset(df.columns):
        return df.copy()
    return add_all_indicators(df)


def _clean_signal(signal: pd.Series, df: pd.DataFrame) -> pd.Series:
    return signal.reindex(df.index).fillna(False).astype(bool)


def generate_volume_breakout_signal(df: pd.DataFrame, params: dict) -> pd.Series:
    result = _ensure_indicators(df)
    merged = _with_default_params("volume_breakout", params)
    signal = (
        (result["close"] > result["high_20"])
        & (result["volume"] > result["avg_volume_20"] * float(merged["volume_multiplier"]))
        & (result["ma20"] > result["ma20"].shift(1))
        & (result["rsi14"] <= float(merged["max_rsi"]))
    )
    return _clean_signal(signal, result)


def generate_pullback_rebound_signal(df: pd.DataFrame, params: dict) -> pd.Series:
    result = _ensure_indicators(df)
    merged = _with_default_params("pullback_rebound", params)
    signal = (
        (result["ma20"] > result["ma20"].shift(1))
        & (result["close"] > result["ma5"])
        & (result["close"].shift(1) <= result["ma5"].shift(1))
        & (result["rsi14"].between(float(merged["min_rsi"]), float(merged["max_rsi"])))
        & (result["rsi14"] > result["rsi14"].shift(1))
        & (result["volume"] > result["avg_volume_20"] * float(merged["volume_multiplier"]))
    )
    return _clean_signal(signal, result)


def generate_oversold_rebound_signal(df: pd.DataFrame, params: dict) -> pd.Series:
    result = _ensure_indicators(df)
    merged = _with_default_params("oversold_rebound", params)
    signal = (
        (result["rsi14"] > float(merged["oversold_rsi"]))
        & (result["rsi14"].shift(1) <= float(merged["oversold_rsi"]))
        & (result["rsi14"] <= float(merged["max_rsi"]))
        & (result["close"] > result["ma5"])
        & (result["macd_hist"] > result["macd_hist"].shift(1))
    )
    return _clean_signal(signal, result)


def generate_ma_bullish_signal(df: pd.DataFrame, params: dict) -> pd.Series:
    result = _ensure_indicators(df)
    merged = _with_default_params("ma_bullish", params)
    signal = (
        (result["ma5"] > result["ma20"])
        & (result["ma20"] > result["ma60"])
        & (result["close"] > result["ma5"])
        & (result["volume"] > result["avg_volume_20"] * float(merged["volume_multiplier"]))
    )
    return _clean_signal(signal, result)


def generate_macd_turn_positive_signal(df: pd.DataFrame, params: dict) -> pd.Series:
    result = _ensure_indicators(df)
    signal = (result["macd_hist"] > 0) & (result["macd_hist"].shift(1) <= 0)
    return _clean_signal(signal, result)


def generate_signal(df: pd.DataFrame, strategy_name: str, params: dict | None = None) -> pd.Series:
    """Generate a boolean signal Series for the selected strategy."""
    handlers = {
        "volume_breakout": generate_volume_breakout_signal,
        "pullback_rebound": generate_pullback_rebound_signal,
        "oversold_rebound": generate_oversold_rebound_signal,
        "ma_bullish": generate_ma_bullish_signal,
        "macd_turn_positive": generate_macd_turn_positive_signal,
    }
    if strategy_name not in handlers:
        raise ValueError(f"Unknown strategy: {strategy_name}")
    return handlers[strategy_name](df, params or {})
