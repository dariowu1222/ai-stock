from __future__ import annotations

import os
import time
from datetime import date, timedelta
from typing import Iterable

import pandas as pd
import requests


SUPABASE_UPSERT_CHUNK_SIZE = 500


class SupabaseWriteError(RuntimeError):
    """Raised when a Supabase write cannot be completed."""


def get_supabase_write_key(config: dict) -> str:
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_ACCESS_TOKEN")
        or str(config.get("supabase_service_role_key", "")).strip()
    )
    if not key:
        raise SupabaseWriteError(
            "Supabase write key not found. Set SUPABASE_SERVICE_ROLE_KEY in the environment."
        )
    return key.strip()


def resolve_supabase_update_start_date(
    start_date: str | None,
    backfill_days: int,
    today: date | None = None,
) -> str:
    if start_date:
        return start_date
    resolved_today = today or date.today()
    return (resolved_today - timedelta(days=int(backfill_days))).isoformat()


def upsert_daily_prices(config: dict, stock_id: str, prices: pd.DataFrame) -> int:
    if prices.empty:
        return 0

    rows = _price_rows(stock_id, prices)
    if not rows:
        return 0

    total = 0
    for chunk in _chunks(rows, SUPABASE_UPSERT_CHUNK_SIZE):
        _request_with_retries(
            "POST",
            _supabase_rest_url(config, "ai_tw_stock_daily_price"),
            config,
            params={"on_conflict": "stock_id,trade_date"},
            json=chunk,
            extra_headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
        )
        total += len(chunk)
    return total


def insert_update_log(config: dict, log_row: dict) -> None:
    _request_with_retries(
        "POST",
        _supabase_rest_url(config, "ai_tw_stock_update_log"),
        config,
        json=[log_row],
        extra_headers={"Prefer": "return=minimal"},
    )


def _price_rows(stock_id: str, prices: pd.DataFrame) -> list[dict]:
    df = prices.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for column in ["open", "high", "low", "close", "volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["date", "open", "high", "low", "close", "volume"])
    df = df.sort_values("date").drop_duplicates("date", keep="last")

    rows = []
    for row in df.itertuples(index=False):
        rows.append(
            {
                "stock_id": stock_id,
                "trade_date": row.date.date().isoformat(),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": int(row.volume),
            }
        )
    return rows


def _supabase_rest_url(config: dict, table: str) -> str:
    base_url = str(config.get("supabase_url", "")).strip().rstrip("/")
    if not base_url:
        raise SupabaseWriteError("config.json missing supabase_url.")
    return f"{base_url}/rest/v1/{table}"


def _supabase_write_headers(config: dict, extra_headers: dict | None = None) -> dict:
    key = get_supabase_write_key(config)
    headers = {
        "apikey": key,
        "Content-Type": "application/json",
    }
    if not key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {key}"
    if extra_headers:
        headers.update(extra_headers)
    return headers


def _request_with_retries(
    method: str,
    url: str,
    config: dict,
    *,
    params: dict | None = None,
    json: list[dict] | dict | None = None,
    extra_headers: dict | None = None,
) -> requests.Response:
    error = ""
    for attempt in range(1, 6):
        try:
            response = requests.request(
                method,
                url,
                headers=_supabase_write_headers(config, extra_headers),
                params=params,
                json=json,
                timeout=120,
            )
            if response.status_code < 400:
                return response
            error = f"HTTP {response.status_code} {response.text[:500]}"
        except requests.RequestException as exc:
            error = repr(exc)

        if attempt < 5:
            time.sleep(2 * attempt)

    raise SupabaseWriteError(f"Supabase write failed after retries: {error}")


def _chunks(rows: list[dict], size: int) -> Iterable[list[dict]]:
    for index in range(0, len(rows), size):
        yield rows[index : index + size]
