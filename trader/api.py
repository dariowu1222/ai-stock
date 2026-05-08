class TradingApiStub:
    def __init__(self):
        self.live_trading_enabled = False

    def place_order(self, *args, **kwargs):
        raise RuntimeError("Live trading is disabled in MVP phase.")
