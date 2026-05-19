"""Shared helpers for the reports/ layer.

Includes:
- Audience modes (controls tone & detail of generated narratives).
- Number / percent formatters.
- Simple SVG sparkline rendering (no extra deps).
- Common indicator snapshot extractor for any single stock dataframe.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

import pandas as pd

from strategy.indicators import add_all_indicators
from strategy.signal_engine import generate_signal
from strategy.templates import list_strategy_templates


AUDIENCE_RETAIL = "retail"          # 散戶：白話結論
AUDIENCE_SELF_TRADE = "self_trade"  # 自己交易：訊號 + 進出場 + 風控
AUDIENCE_PRO = "pro"                # 法人風格：完整數據附錄

AUDIENCE_LABELS = {
    AUDIENCE_RETAIL: "散戶速讀",
    AUDIENCE_SELF_TRADE: "自己交易",
    AUDIENCE_PRO: "法人完整",
}


@dataclass
class StockSnapshot:
    """Latest-row snapshot of indicators + signals for one stock."""

    stock_id: str
    stock_name: str
    industry: str
    market: str
    as_of: str
    close: float
    daily_change_pct: float
    high_52w: float
    low_52w: float
    ret_5d: float
    ret_20d: float
    ret_60d: float
    ma5: float
    ma20: float
    ma60: float
    rsi14: float
    macd: float
    macd_signal: float
    macd_hist: float
    k: float
    d: float
    bias: float
    atr14: float
    high_20: float
    low_20: float
    avg_volume_20: float
    volume: int
    triggered_strategies: list[str]


def fmt_pct(value: float | None, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value * 100:.{digits}f}%"


def fmt_num(value: float | None, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:,.{digits}f}"


def fmt_int(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{int(value):,}"


def build_snapshot(
    stock_id: str,
    stock_name: str,
    industry: str,
    market: str,
    prices: pd.DataFrame,
    *,
    detect_signals: bool = True,
) -> StockSnapshot:
    """Compute the indicator + signal snapshot used by every report."""

    if prices is None or prices.empty:
        raise ValueError(f"No price data for {stock_id}")

    df = add_all_indicators(prices.sort_values("date").reset_index(drop=True))
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last

    daily_change = (last["close"] - prev["close"]) / prev["close"] if prev["close"] else 0.0
    ret_5d = _return_n(df, 5)
    ret_20d = _return_n(df, 20)
    ret_60d = _return_n(df, 60)
    window_52w = df.tail(252)

    triggered: list[str] = []
    if detect_signals:
        for template in list_strategy_templates():
            try:
                signal = generate_signal(df, template["strategy_name"])
                if bool(signal.iloc[-1]):
                    triggered.append(template["strategy_name"])
            except Exception:
                continue

    return StockSnapshot(
        stock_id=str(stock_id),
        stock_name=stock_name or "",
        industry=industry or "",
        market=market or "",
        as_of=pd.to_datetime(last["date"]).strftime("%Y-%m-%d"),
        close=float(last["close"]),
        daily_change_pct=float(daily_change),
        high_52w=float(window_52w["high"].max()),
        low_52w=float(window_52w["low"].min()),
        ret_5d=ret_5d,
        ret_20d=ret_20d,
        ret_60d=ret_60d,
        ma5=_safe_float(last.get("ma5")),
        ma20=_safe_float(last.get("ma20")),
        ma60=_safe_float(last.get("ma60")),
        rsi14=_safe_float(last.get("rsi14")),
        macd=_safe_float(last.get("macd")),
        macd_signal=_safe_float(last.get("macd_signal")),
        macd_hist=_safe_float(last.get("macd_hist")),
        k=_safe_float(last.get("k")),
        d=_safe_float(last.get("d")),
        bias=_safe_float(last.get("bias")),
        atr14=_safe_float(last.get("atr14")),
        high_20=_safe_float(last.get("high_20")),
        low_20=_safe_float(last.get("low_20")),
        avg_volume_20=_safe_float(last.get("avg_volume_20")),
        volume=int(last["volume"]) if not pd.isna(last["volume"]) else 0,
        triggered_strategies=triggered,
    )


def sparkline_svg(values: Iterable[float], width: int = 220, height: int = 48, color: str = "#1f6feb") -> str:
    """Inline SVG sparkline. No deps. Auto-scales to min/max."""
    series = [float(v) for v in values if v is not None and not pd.isna(v)]
    if len(series) < 2:
        return f'<svg width="{width}" height="{height}"></svg>'
    lo, hi = min(series), max(series)
    span = max(hi - lo, 1e-9)
    n = len(series)
    points = []
    for i, v in enumerate(series):
        x = i * (width - 4) / (n - 1) + 2
        y = height - 2 - (v - lo) / span * (height - 4)
        points.append(f"{x:.1f},{y:.1f}")
    path = " ".join(points)
    last_x, last_y = points[-1].split(",")
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<polyline fill="none" stroke="{color}" stroke-width="1.6" points="{path}"/>'
        f'<circle cx="{last_x}" cy="{last_y}" r="2.4" fill="{color}"/>'
        "</svg>"
    )


def trend_label(snap: StockSnapshot) -> str:
    if snap.ma5 and snap.ma20 and snap.ma60 and snap.ma5 > snap.ma20 > snap.ma60:
        return "多頭排列"
    if snap.ma5 and snap.ma20 and snap.ma60 and snap.ma5 < snap.ma20 < snap.ma60:
        return "空頭排列"
    return "盤整 / 糾結"


def momentum_label(snap: StockSnapshot) -> str:
    if pd.isna(snap.rsi14):
        return "—"
    if snap.rsi14 >= 70:
        return "RSI 偏熱"
    if snap.rsi14 <= 30:
        return "RSI 偏冷"
    return "RSI 中性"


def report_disclaimer() -> str:
    return (
        "本報告由 AI 台股工具自動生成，僅供研究與決策輔助，"
        "不構成投資建議。投資涉及風險，過往績效不代表未來。"
    )


def today_str() -> str:
    return date.today().strftime("%Y-%m-%d")


# ---------- helpers ----------


def _return_n(df: pd.DataFrame, n: int) -> float:
    if len(df) <= n:
        return 0.0
    last_close = df["close"].iloc[-1]
    past_close = df["close"].iloc[-n - 1]
    if not past_close:
        return 0.0
    return float((last_close - past_close) / past_close)


def _safe_float(value) -> float:
    if value is None:
        return float("nan")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")
