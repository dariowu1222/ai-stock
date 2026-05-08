from __future__ import annotations

import argparse
import json
import time
from datetime import date, datetime
from pathlib import Path

from data.finmind import FinMindError, get_finmind_token, resolve_update_start_date, update_stock_price_csv
from data.loader import load_stock_pool


def load_config(path: str = "config.json") -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_update_status(output_dir: str, status: dict) -> None:
    path = Path(output_dir) / "price_update_status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update local Taiwan stock price CSV files from FinMind.")
    parser.add_argument("--config", default="config.json", help="Path to config.json.")
    parser.add_argument("--start-date", default=None, help="Override update start date, YYYY-MM-DD.")
    parser.add_argument("--end-date", default=None, help="Override update end date, YYYY-MM-DD.")
    parser.add_argument("--stock-id", action="append", default=None, help="Update only this stock id. Can repeat.")
    parser.add_argument("--limit", type=int, default=None, help="Update only first N stocks from selected pool.")
    parser.add_argument("--sleep", type=float, default=None, help="Seconds to sleep between API requests.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    data_dir = config.get("data_dir", "price_data")
    output_dir = config.get("output_dir", "output")
    watchlist_path = config.get("stock_pool_file", "watchlist.json")
    default_start_date = config.get("price_history_start_date", "2020-01-01")
    backfill_days = int(config.get("price_update_backfill_days", 5))
    sleep_seconds = float(
        args.sleep
        if args.sleep is not None
        else config.get("finmind_request_sleep_seconds", 0.8)
    )
    end_date = args.end_date or date.today().isoformat()

    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = {
        "source": "FinMind",
        "started_at": started_at,
        "finished_at": "",
        "end_date": end_date,
        "success_count": 0,
        "fail_count": 0,
        "stocks": [],
        "status": "running",
    }
    write_update_status(output_dir, status)

    try:
        token = get_finmind_token()
    except FinMindError as exc:
        print(f"ERROR: {exc}")
        print("請先設定 FINMIND_TOKEN，或建立 secrets/finmind_token.txt。")
        status["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status["status"] = "failed"
        status["error"] = str(exc)
        write_update_status(output_dir, status)
        return 2

    stock_pool = load_stock_pool(watchlist_path)
    if args.stock_id:
        selected_ids = set(args.stock_id)
        stock_pool = [stock for stock in stock_pool if str(stock.get("stock_id")) in selected_ids]
    if args.limit:
        stock_pool = stock_pool[: args.limit]

    if not stock_pool:
        print("No stocks selected.")
        status["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status["status"] = "failed"
        status["error"] = "No stocks selected."
        write_update_status(output_dir, status)
        return 1

    print(f"Updating {len(stock_pool)} stock(s) from FinMind.")
    print(f"Data dir: {data_dir}")
    print(f"End date: {end_date}")
    print("Token: SET")

    success_count = 0
    fail_count = 0
    for index, stock in enumerate(stock_pool, start=1):
        stock_id = str(stock.get("stock_id", "")).strip()
        stock_name = str(stock.get("stock_name", "")).strip()
        if not stock_id:
            continue

        csv_path = Path(data_dir) / f"{stock_id}.csv"
        start_date = args.start_date or resolve_update_start_date(
            csv_path,
            default_start_date,
            backfill_days=backfill_days,
        )
        label = f"{stock_id} {stock_name}".strip()
        try:
            result = update_stock_price_csv(
                stock_id,
                data_dir,
                start_date=start_date,
                end_date=end_date,
                token=token,
            )
            success_count += 1
            status["stocks"].append(
                {
                    "stock_id": stock_id,
                    "stock_name": stock_name,
                    "status": "ok",
                    "fetched_rows": result["fetched_rows"],
                    "total_rows": result["total_rows"],
                    "latest_date": result["latest_date"],
                }
            )
            print(
                f"[{index}/{len(stock_pool)}] OK {label}: "
                f"fetched={result['fetched_rows']}, total={result['total_rows']}, "
                f"latest={result['latest_date']}"
            )
        except Exception as exc:
            fail_count += 1
            status["stocks"].append(
                {
                    "stock_id": stock_id,
                    "stock_name": stock_name,
                    "status": "failed",
                    "error": str(exc),
                }
            )
            print(f"[{index}/{len(stock_pool)}] FAIL {label}: {exc}")

        if index < len(stock_pool) and sleep_seconds > 0:
            time.sleep(sleep_seconds)

    print(f"Done. success={success_count}, failed={fail_count}")
    status["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status["success_count"] = success_count
    status["fail_count"] = fail_count
    status["status"] = "ok" if success_count > 0 and fail_count == 0 else "partial_failed"
    write_update_status(output_dir, status)
    return 0 if success_count > 0 and fail_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
