import pandas as pd

from strategy.indicators import add_all_indicators
from strategy.signal_engine import generate_signal
from strategy.templates import get_strategy_template


OUTPUT_COLUMNS = [
    "stock_id",
    "stock_name",
    "strategy_name",
    "strategy_display",
    "signal_date",
    "close",
    "volume",
    "rsi14",
    "ma5",
    "ma20",
    "ma60",
    "technical_score",
    "reason",
]


def screen_stocks(
    price_data: dict[str, pd.DataFrame],
    stock_pool: list[dict],
    strategy_name: str,
    params: dict | None = None,
) -> pd.DataFrame:
    """Screen latest-day strategy signals for the stock pool."""
    template = get_strategy_template(strategy_name)
    rows = []

    for stock in stock_pool:
        stock_id = str(stock.get("stock_id", "")).strip()
        df = price_data.get(stock_id)
        if df is None or df.empty:
            continue

        data = add_all_indicators(df)
        signal = generate_signal(data, strategy_name, params)
        if signal.empty or not bool(signal.iloc[-1]):
            continue

        latest = data.iloc[-1]
        row = {
            "stock_id": stock_id,
            "stock_name": stock.get("stock_name", ""),
            "strategy_name": strategy_name,
            "strategy_display": template["display_name"],
            "signal_date": latest["date"],
            "close": latest["close"],
            "volume": latest["volume"],
            "rsi14": latest.get("rsi14"),
            "ma5": latest.get("ma5"),
            "ma20": latest.get("ma20"),
            "ma60": latest.get("ma60"),
            "reason": _build_reason(strategy_name, latest),
        }
        row["technical_score"] = calculate_technical_score(pd.Series(row))
        rows.append(row)

    if not rows:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)


def calculate_technical_score(row: pd.Series) -> float:
    score = 0.0
    close = row.get("close")
    ma5 = row.get("ma5")
    ma20 = row.get("ma20")
    ma60 = row.get("ma60")
    rsi14 = row.get("rsi14")
    volume = row.get("volume")

    if pd.notna(close) and pd.notna(ma5) and close > ma5:
        score += 20
    if pd.notna(ma5) and pd.notna(ma20) and ma5 > ma20:
        score += 20
    if pd.notna(ma20) and pd.notna(ma60) and ma20 > ma60:
        score += 20
    if pd.notna(rsi14) and 45 <= float(rsi14) <= 75:
        score += 20
    elif pd.notna(rsi14) and 35 <= float(rsi14) < 45:
        score += 10
    if pd.notna(volume) and float(volume) > 0:
        score += 20
    return round(score, 2)


def _build_reason(strategy_name: str, latest: pd.Series) -> str:
    if strategy_name == "volume_breakout":
        return "收盤突破前高且量能放大，趨勢仍需避免追高。"
    if strategy_name == "pullback_rebound":
        return "MA20 向上，股價重新站回短均，RSI 回升。"
    if strategy_name == "oversold_rebound":
        return "RSI 低檔回升且 MACD 動能改善。"
    if strategy_name == "ma_bullish":
        return "均線呈多頭排列，收盤在短均上方且量能高於均量。"
    if strategy_name == "macd_turn_positive":
        return "MACD histogram 由負轉正，動能初步改善。"
    return "符合策略條件。"
