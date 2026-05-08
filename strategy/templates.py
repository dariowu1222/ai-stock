_STRATEGY_TEMPLATES = [
    {
        "strategy_name": "volume_breakout",
        "display_name": "爆量突破",
        "description": "收盤突破前 20 日高點，成交量放大，MA20 向上，RSI 未過熱。",
        "default_params": {"volume_multiplier": 1.5, "max_rsi": 80},
    },
    {
        "strategy_name": "pullback_rebound",
        "display_name": "回檔轉強",
        "description": "MA20 向上，股價重新站回 MA5，RSI 回升且量能溫和放大。",
        "default_params": {"min_rsi": 35, "max_rsi": 75, "volume_multiplier": 1.05},
    },
    {
        "strategy_name": "oversold_rebound",
        "display_name": "超跌反彈",
        "description": "RSI 低檔回升，收盤站回 MA5，MACD histogram 改善。",
        "default_params": {"oversold_rsi": 40, "max_rsi": 65},
    },
    {
        "strategy_name": "ma_bullish",
        "display_name": "均線多頭",
        "description": "MA5 > MA20 > MA60，收盤在 MA5 上方，成交量大於 20 日均量。",
        "default_params": {"volume_multiplier": 1.0},
    },
    {
        "strategy_name": "macd_turn_positive",
        "display_name": "MACD 翻正",
        "description": "MACD histogram 由負轉正。",
        "default_params": {},
    },
]


def get_strategy_template(strategy_name: str) -> dict:
    for template in _STRATEGY_TEMPLATES:
        if template["strategy_name"] == strategy_name:
            return template.copy()
    raise ValueError(f"Unknown strategy: {strategy_name}")


def list_strategy_templates() -> list[dict]:
    return [template.copy() for template in _STRATEGY_TEMPLATES]
