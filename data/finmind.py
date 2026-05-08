from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests


API_URL = "https://api.finmindtrade.com/api/v4/data"
PRICE_COLUMNS = ["date", "open", "high", "low", "close", "volume"]


class FinMindError(RuntimeError):
    """Raised when FinMind returns an error or unusable data."""


def get_finmind_token(token: str | None = None, token_file: str | None = None) -> str:
    """Read FinMind token from argument, env, Windows user env, or local file."""
    if token:
        return token.strip()

    env_token = os.environ.get("FINMIND_TOKEN")
    if env_token:
        return env_token.strip()

    registry_token = _read_windows_user_env("FINMIND_TOKEN")
    if registry_token:
        return registry_token.strip()

    paths = []
    if token_file:
        paths.append(Path(token_file))
    paths.extend([Path("secrets") / "finmind_token.txt", Path("finmind_token.txt")])
    for path in paths:
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value

    raise FinMindError(
        "FinMind token not found. Set FINMIND_TOKEN or create secrets/finmind_token.txt."
    )


def fetch_taiwan_stock_price(
    stock_id: str,
    start_date: str,
    end_date: str | None = None,
    token: str | None = None,
    timeout: int = 30,
) -> pd.DataFrame:
    """Fetch TaiwanStockPrice from FinMind and normalize it to local OHLCV format."""
    resolved_token = get_finmind_token(token)
    headers = {"Authorization": f"Bearer {resolved_token}"}
    params: dict[str, Any] = {
        "dataset": "TaiwanStockPrice",
        "data_id": stock_id,
        "start_date": start_date,
    }
    if end_date:
        params["end_date"] = end_date

    response = requests.get(API_URL, headers=headers, params=params, timeout=timeout)
    payload = _parse_response(response, stock_id)
    raw = pd.DataFrame(payload["data"])
    return normalize_taiwan_stock_price(raw, stock_id)


def normalize_taiwan_stock_price(df: pd.DataFrame, stock_id: str) -> pd.DataFrame:
    """Convert FinMind TaiwanStockPrice schema to date/open/high/low/close/volume."""
    if df.empty:
        return pd.DataFrame(columns=PRICE_COLUMNS)

    required = ["date", "open", "max", "min", "close", "Trading_Volume"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise FinMindError(f"{stock_id} response missing columns: {missing}")

    result = df.rename(
        columns={
            "max": "high",
            "min": "low",
            "Trading_Volume": "volume",
        }
    )[PRICE_COLUMNS].copy()

    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    for column in ["open", "high", "low", "close", "volume"]:
        result[column] = pd.to_numeric(result[column], errors="coerce")

    result = result.dropna(subset=PRICE_COLUMNS)
    result["volume"] = result["volume"].astype("int64")
    return result.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)


def merge_price_data(existing: pd.DataFrame | None, incoming: pd.DataFrame) -> pd.DataFrame:
    """Merge existing local CSV data with freshly fetched data."""
    frames = []
    if existing is not None and not existing.empty:
        frames.append(existing[PRICE_COLUMNS].copy())
    if not incoming.empty:
        frames.append(incoming[PRICE_COLUMNS].copy())

    if not frames:
        return pd.DataFrame(columns=PRICE_COLUMNS)

    merged = pd.concat(frames, ignore_index=True)
    merged["date"] = pd.to_datetime(merged["date"], errors="coerce")
    for column in ["open", "high", "low", "close", "volume"]:
        merged[column] = pd.to_numeric(merged[column], errors="coerce")
    merged = merged.dropna(subset=PRICE_COLUMNS)
    merged["volume"] = merged["volume"].astype("int64")
    return merged.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)


def save_price_csv(df: pd.DataFrame, csv_path: str | Path) -> None:
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    output = df.copy()
    output["date"] = pd.to_datetime(output["date"]).dt.strftime("%Y-%m-%d")
    output.to_csv(path, columns=PRICE_COLUMNS, index=False, encoding="utf-8")


def resolve_update_start_date(
    csv_path: str | Path,
    default_start_date: str,
    backfill_days: int = 5,
) -> str:
    """Use latest local date minus backfill days, or default start date if no CSV exists."""
    path = Path(csv_path)
    if not path.exists():
        return default_start_date

    try:
        df = pd.read_csv(path, usecols=["date"])
    except Exception:
        return default_start_date

    if df.empty:
        return default_start_date

    latest = pd.to_datetime(df["date"], errors="coerce").max()
    if pd.isna(latest):
        return default_start_date
    return (latest.date() - timedelta(days=int(backfill_days))).isoformat()


def update_stock_price_csv(
    stock_id: str,
    data_dir: str | Path,
    start_date: str,
    end_date: str | None = None,
    token: str | None = None,
) -> dict:
    """Fetch one stock and persist it to the local CSV cache."""
    csv_path = Path(data_dir) / f"{stock_id}.csv"
    incoming = fetch_taiwan_stock_price(stock_id, start_date, end_date=end_date, token=token)
    existing = _read_existing_price_csv(csv_path)
    merged = merge_price_data(existing, incoming)
    save_price_csv(merged, csv_path)

    return {
        "stock_id": stock_id,
        "csv_path": str(csv_path),
        "fetched_rows": int(len(incoming)),
        "total_rows": int(len(merged)),
        "latest_date": _latest_date_text(merged),
    }


def _parse_response(response: requests.Response, stock_id: str) -> dict:
    try:
        payload = response.json()
    except ValueError as exc:
        raise FinMindError(f"{stock_id} returned non-JSON response: HTTP {response.status_code}") from exc

    status = int(payload.get("status", response.status_code) or response.status_code)
    if response.status_code >= 400 or status >= 400:
        message = payload.get("msg") or payload.get("message") or response.text
        raise FinMindError(f"{stock_id} FinMind error HTTP {response.status_code}, status {status}: {message}")

    if "data" not in payload or payload["data"] is None:
        raise FinMindError(f"{stock_id} response has no data field.")
    return payload


def _read_existing_price_csv(csv_path: Path) -> pd.DataFrame | None:
    if not csv_path.exists():
        return None
    df = pd.read_csv(csv_path)
    if df.empty:
        return pd.DataFrame(columns=PRICE_COLUMNS)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df[PRICE_COLUMNS]


def _latest_date_text(df: pd.DataFrame) -> str:
    if df.empty:
        return ""
    latest = pd.to_datetime(df["date"]).max()
    return latest.strftime("%Y-%m-%d")


def _read_windows_user_env(name: str) -> str | None:
    if not sys.platform.startswith("win"):
        return None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value)
    except Exception:
        return None
