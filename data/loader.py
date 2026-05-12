import json
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests


REQUIRED_COLUMNS = ["date", "open", "high", "low", "close", "volume"]
SUPABASE_PAGE_SIZE = 1000


def _supabase_headers(config: dict) -> dict[str, str]:
    api_key = str(config.get("supabase_publishable_key", "")).strip()
    if not api_key:
        raise ValueError("config.json missing supabase_publishable_key.")
    return {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
    }


def _supabase_url(config: dict, table: str) -> str:
    base_url = str(config.get("supabase_url", "")).strip().rstrip("/")
    if not base_url:
        raise ValueError("config.json missing supabase_url.")
    return f"{base_url}/rest/v1/{table}"


def _fetch_supabase_rows(config: dict, table: str, params: dict) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    headers = _supabase_headers(config)
    url = _supabase_url(config, table)
    while True:
        page_params = {
            **params,
            "limit": SUPABASE_PAGE_SIZE,
            "offset": offset,
        }
        for attempt in range(1, 6):
            try:
                response = requests.get(url, headers=headers, params=page_params, timeout=120)
                if response.status_code < 400:
                    break
                error = f"HTTP {response.status_code} {response.text[:500]}"
            except requests.RequestException as exc:
                error = repr(exc)

            if attempt == 5:
                raise RuntimeError(f"Supabase read {table} failed after retries: {error}")
            time.sleep(2 * attempt)

        page = response.json()
        if not isinstance(page, list):
            raise RuntimeError(f"Supabase read {table} returned unexpected payload.")
        rows.extend(page)
        if len(page) < SUPABASE_PAGE_SIZE:
            return rows
        offset += SUPABASE_PAGE_SIZE


def load_stock_pool(watchlist_path: str) -> list[dict]:
    """Load watchlist.json."""
    path = Path(watchlist_path)
    if not path.exists():
        raise FileNotFoundError(f"Watchlist file not found: {watchlist_path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("watchlist.json must be a list of stock objects.")
    return data


def load_stock_pool_from_supabase(config: dict) -> list[dict]:
    rows = _fetch_supabase_rows(
        config,
        "ai_tw_stock_pool",
        {
            "select": "stock_id,stock_name,market,industry_category,rank",
            "order": "rank.asc",
        },
    )
    return [
        {
            "stock_id": str(row.get("stock_id", "")).strip(),
            "stock_name": str(row.get("stock_name", "")).strip(),
            "market": str(row.get("market", "")).strip(),
            "industry_category": str(row.get("industry_category", "")).strip(),
        }
        for row in rows
        if str(row.get("stock_id", "")).strip()
    ]


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
    skipped = []
    base_dir = Path(data_dir)
    for stock in stock_pool:
        stock_id = str(stock.get("stock_id", "")).strip()
        if not stock_id:
            continue
        csv_path = base_dir / f"{stock_id}.csv"
        try:
            prices[stock_id] = load_price_csv(str(csv_path))
        except Exception as exc:
            skipped.append(f"{stock_id}: {exc}")
    if skipped:
        preview = "; ".join(skipped[:5])
        suffix = " ..." if len(skipped) > 5 else ""
        print(f"[load_all_prices] skipped {len(skipped)} stock(s): {preview}{suffix}")
    return prices


def load_all_prices_from_supabase(config: dict, stock_pool: list[dict]) -> dict[str, pd.DataFrame]:
    stock_ids = {
        str(stock.get("stock_id", "")).strip()
        for stock in stock_pool
        if str(stock.get("stock_id", "")).strip()
    }
    params = {
        "select": "stock_id,trade_date,open,high,low,close,volume",
        "order": "stock_id.asc,trade_date.asc",
    }
    history_days = int(config.get("supabase_history_days", 0) or 0)
    if history_days > 0:
        start_date = date.today() - timedelta(days=history_days)
        params["trade_date"] = f"gte.{start_date.isoformat()}"

    rows = _fetch_supabase_rows(config, "ai_tw_stock_daily_price", params)
    if not rows:
        return {}

    df = pd.DataFrame(rows)
    df = df[df["stock_id"].astype(str).isin(stock_ids)].copy()
    if df.empty:
        return {}
    df = df.rename(columns={"trade_date": "date"})
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for column in ["open", "high", "low", "close", "volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=REQUIRED_COLUMNS)
    df["volume"] = df["volume"].astype("int64")

    prices: dict[str, pd.DataFrame] = {}
    for stock_id, group in df.groupby("stock_id", sort=False):
        prices[str(stock_id)] = group[REQUIRED_COLUMNS].sort_values("date").reset_index(drop=True)
    return prices
