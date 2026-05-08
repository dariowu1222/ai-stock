import json
from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = ["date", "open", "high", "low", "close", "volume"]


def load_stock_pool(watchlist_path: str) -> list[dict]:
    """Load watchlist.json."""
    path = Path(watchlist_path)
    if not path.exists():
        raise FileNotFoundError(f"Watchlist file not found: {watchlist_path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("watchlist.json must be a list of stock objects.")
    return data


def load_price_csv(csv_path: str) -> pd.DataFrame:
    """Load one stock OHLCV CSV and return sorted price data."""
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    df = pd.read_csv(path)
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"{csv_path} missing required columns: {missing}")

    df = df[REQUIRED_COLUMNS].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if df["date"].isna().any():
        raise ValueError(f"{csv_path} contains invalid date values.")

    for column in ["open", "high", "low", "close", "volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    if df[["open", "high", "low", "close", "volume"]].isna().any().any():
        raise ValueError(f"{csv_path} contains non-numeric OHLCV values.")

    return df.sort_values("date").reset_index(drop=True)


def load_all_prices(data_dir: str, stock_pool: list[dict]) -> dict[str, pd.DataFrame]:
    """Load all CSV files for stocks in the pool.

    Missing or invalid files are skipped so one bad stock does not crash the
    whole MVP flow.
    """
    prices: dict[str, pd.DataFrame] = {}
    base_dir = Path(data_dir)
    for stock in stock_pool:
        stock_id = str(stock.get("stock_id", "")).strip()
        if not stock_id:
            continue
        csv_path = base_dir / f"{stock_id}.csv"
        try:
            prices[stock_id] = load_price_csv(str(csv_path))
        except Exception as exc:
            print(f"[load_all_prices] skip {stock_id}: {exc}")
    return prices
