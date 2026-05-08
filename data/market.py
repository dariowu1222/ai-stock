def get_market_context() -> dict:
    return {
        "market_regime": "震盪偏多",
        "risk_level": "medium",
        "market_score": 15,
        "preferred_strategies": ["pullback_rebound", "ma_bullish"],
        "avoid_strategies": ["volume_breakout"],
        "summary": "目前大盤偏多但接近壓力區，適合回檔轉強與均線多頭，不適合高檔爆量追價。",
    }
