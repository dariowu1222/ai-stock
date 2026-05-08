import pandas as pd


def calculate_backtest_metrics(trades: pd.DataFrame) -> dict:
    """Calculate metrics from net returns without division-by-zero failures."""
    if trades.empty:
        return {
            "trade_count": 0,
            "win_rate": 0,
            "avg_return": 0,
            "avg_win": 0,
            "avg_loss": 0,
            "profit_loss_ratio": 0,
            "max_drawdown": 0,
            "max_losing_streak": 0,
            "avg_holding_days": 0,
            "total_return": 0,
        }

    returns = trades["net_return"].astype(float)
    wins = returns[returns > 0]
    losses = returns[returns <= 0]
    equity = (1 + returns).cumprod()
    drawdown = equity / equity.cummax() - 1

    max_losing_streak = 0
    current_streak = 0
    for value in returns:
        if value <= 0:
            current_streak += 1
            max_losing_streak = max(max_losing_streak, current_streak)
        else:
            current_streak = 0

    avg_win = float(wins.mean()) if not wins.empty else 0
    avg_loss = float(losses.mean()) if not losses.empty else 0
    profit_loss_ratio = avg_win / abs(avg_loss) if avg_loss < 0 else 0

    return {
        "trade_count": int(len(trades)),
        "win_rate": float((returns > 0).mean()),
        "avg_return": float(returns.mean()),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_loss_ratio": float(profit_loss_ratio),
        "max_drawdown": float(drawdown.min()),
        "max_losing_streak": int(max_losing_streak),
        "avg_holding_days": float(trades["holding_days"].mean()),
        "total_return": float(equity.iloc[-1] - 1),
    }
