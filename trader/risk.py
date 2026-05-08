def check_live_trading_allowed(config: dict) -> bool:
    return bool(config.get("enable_live_trading") is True)
