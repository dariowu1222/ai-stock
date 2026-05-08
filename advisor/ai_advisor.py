from strategy.templates import get_strategy_template, list_strategy_templates


def recommend_strategies(market_context: dict) -> list[dict]:
    """Recommend testable strategies from local market context.

    This MVP uses deterministic rules only. It does not call any LLM and does
    not directly recommend buy/sell actions.
    """
    preferred = market_context.get("preferred_strategies") or []
    templates = {item["strategy_name"]: item for item in list_strategy_templates()}

    recommendations = []
    for strategy_name in preferred:
        if strategy_name in templates:
            template = templates[strategy_name]
            recommendations.append(
                {
                    "strategy_name": strategy_name,
                    "display_name": template["display_name"],
                    "params": template["default_params"],
                    "reason": f"目前市場情境適合測試「{template['display_name']}」。",
                }
            )

    if not recommendations:
        template = get_strategy_template("ma_bullish")
        recommendations.append(
            {
                "strategy_name": "ma_bullish",
                "display_name": template["display_name"],
                "params": template["default_params"],
                "reason": "市場方向不明時，優先用均線多頭檢查趨勢股。",
            }
        )

    return recommendations


def build_stock_report(
    stock_row: dict,
    backtest_metrics: dict | None,
    market_context: dict,
    chip_context: dict | None = None,
) -> dict:
    """Build a structured decision-support report for one stock."""
    metrics = backtest_metrics or {"trade_count": 0}
    chip = chip_context or {}
    trade_count = int(metrics.get("trade_count", 0) or 0)
    avg_return = float(metrics.get("avg_return", 0) or 0)
    win_rate = float(metrics.get("win_rate", 0) or 0)

    if trade_count < 5:
        suggestion = "觀察，回測樣本數不足，需等待更多確認。"
    elif avg_return > 0 and win_rate >= 0.5:
        suggestion = "列入觀察，不建議追高，需搭配停損與風險控管。"
    else:
        suggestion = "等待確認，目前策略優勢不明顯。"

    return {
        "stock_id": stock_row.get("stock_id", ""),
        "stock_name": stock_row.get("stock_name", ""),
        "strategy_name": stock_row.get("strategy_name", ""),
        "strategy_display": stock_row.get("strategy_display", stock_row.get("strategy_name", "")),
        "signal_date": str(stock_row.get("signal_date", "")),
        "technical": {
            "close": stock_row.get("close"),
            "volume": stock_row.get("volume"),
            "rsi14": stock_row.get("rsi14"),
            "ma5": stock_row.get("ma5"),
            "ma20": stock_row.get("ma20"),
            "ma60": stock_row.get("ma60"),
            "technical_score": stock_row.get("technical_score"),
            "reason": stock_row.get("reason", ""),
        },
        "backtest": metrics,
        "chip": {
            "chip_score": chip.get("chip_score", 0),
            "summary": chip.get("summary", "第一版尚未接籌碼資料。"),
        },
        "market": market_context,
        "risks": [
            "回測樣本數不足時可信度下降。",
            "策略分數只作為輔助，不代表未來績效。",
            "若價格跌破關鍵均線或市場轉弱，策略可能失效。",
        ],
        "suggestion": suggestion,
    }
