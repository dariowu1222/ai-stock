import pandas as pd


def run_backtest(
    df: pd.DataFrame,
    signal: pd.Series,
    holding_days: int = 5,
    trade_cost_rate: float = 0.004425,
) -> pd.DataFrame:
    """Run a simple next-open entry, fixed-holding-days exit backtest."""
    if df.empty:
        return _empty_trades()

    data = df.sort_values("date").reset_index(drop=True).copy()
    aligned_signal = signal.reset_index(drop=True).reindex(data.index).fillna(False).astype(bool)
    trades = []
    last_exit_index = -1

    for signal_index, is_signal in aligned_signal.items():
        if not is_signal or signal_index <= last_exit_index:
            continue

        entry_index = signal_index + 1
        exit_index = entry_index + int(holding_days)
        if exit_index >= len(data):
            continue

        entry_price = float(data.loc[entry_index, "open"])
        exit_price = float(data.loc[exit_index, "close"])
        if entry_price <= 0:
            continue

        gross_return = (exit_price / entry_price) - 1
        net_return = gross_return - float(trade_cost_rate)
        trades.append(
            {
                "signal_date": data.loc[signal_index, "date"],
                "entry_date": data.loc[entry_index, "date"],
                "entry_price": entry_price,
                "exit_date": data.loc[exit_index, "date"],
                "exit_price": exit_price,
                "holding_days": int(holding_days),
                "gross_return": gross_return,
                "net_return": net_return,
                "is_win": net_return > 0,
            }
        )
        last_exit_index = exit_index

    if not trades:
        return _empty_trades()
    return pd.DataFrame(trades)


def _empty_trades() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "signal_date",
            "entry_date",
            "entry_price",
            "exit_date",
            "exit_price",
            "holding_days",
            "gross_return",
            "net_return",
            "is_win",
        ]
    )
