from __future__ import annotations

import argparse
import json
import time
from datetime import date, datetime
from pathlib import Path

from data.finmind import (
    FinMindError,
    fetch_taiwan_stock_price,
    get_finmind_token,
    resolve_update_start_date,
    update_stock_price_csv,
)
from data.loader import load_stock_pool, load_stock_pool_from_supabase
from data.supabase_writer import (
    SupabaseWriteError,
    get_supabase_write_key,
    insert_update_log,
    resolve_supabase_update_start_date,
    upsert_daily_prices,
)


def load_config(path: str = "config.json") -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_update_status(output_dir: str, status: dict) -> None:
    path = Path(output_dir) / "price_update_status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update Taiwan stock price data from FinMind.")
    parser.add_argument("--config", default="config.json", help="Path to config.json.")
    parser.add_argument(
        "--target",
        choices=["supabase", "local"],
        default=None,
        help="Write target. Defaults to supabase when config data_source=supabase, otherwise local.",
    )
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
    target = args.target or ("supabase" if config.get("data_source") == "supabase" else "local")
    sleep_seconds = float(
        args.sleep
        if args.sleep is not None
        else config.get("finmind_request_sleep_seconds", 0.8)
    )
    end_date = args.end_date or date.today().isoformat()
    supabase_start_date = resolve_supabase_update_start_date(args.start_date, backfill_days)

    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = {
        "source": "FinMind",
        "target": target,
        "started_at": started_at,
        "finished_at": "",
        "start_date": args.start_date or supabase_start_date,
        "end_date": end_date,
        "success_count": 0,
        "fail_count": 0,
        "fetched_rows": 0,
        "written_rows": 0,
        "stocks": [],
        "status": "running",
    }
    write_update_status(output_dir, status)

    try:
        token = get_finmind_token()
    except FinMindError as exc:
        print(f"ERROR: {exc}")
        print("Set FINMIND_TOKEN or create secrets/finmind_token.txt.")
        status["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status["status"] = "failed"
        status["error"] = str(exc)
        write_update_status(output_dir, status)
        return 2

    if target == "supabase":
        try:
            get_supabase_write_key(config)
        except SupabaseWriteError as exc:
            print(f"ERROR: {exc}")
            status["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            status["status"] = "failed"
            status["error"] = str(exc)
            write_update_status(output_dir, status)
            return 2

    try:
        stock_pool = load_stock_pool_from_supabase(config) if target == "supabase" else load_stock_pool(watchlist_path)
    except Exception as exc:
        print(f"ERROR: failed to load stock pool for target={target}: {exc}")
        status["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status["status"] = "failed"
        status["error"] = str(exc)
        write_update_status(output_dir, status)
        return 2

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
    print(f"Target: {target}")
    if target == "local":
        print(f"Data dir: {data_dir}")
    print(f"End date: {end_date}")
    print("Token: SET")

    success_count = 0
    fail_count = 0
    fetched_total = 0
    written_total = 0
    for index, stock in enumerate(stock_pool, start=1):
        stock_id = str(stock.get("stock_id", "")).strip()
        stock_name = str(stock.get("stock_name", "")).strip()
        if not stock_id:
            continue

        if target == "supabase":
            start_date = supabase_start_date
        else:
            csv_path = Path(data_dir) / f"{stock_id}.csv"
            start_date = args.start_date or resolve_update_start_date(
                csv_path,
                default_start_date,
                backfill_days=backfill_days,
            )

        label = f"{stock_id} {stock_name}".strip()
        try:
            if target == "supabase":
                incoming = fetch_taiwan_stock_price(stock_id, start_date, end_date=end_date, token=token)
                written_rows = upsert_daily_prices(config, stock_id, incoming)
                latest_date = ""
                if not incoming.empty:
                    latest_date = incoming["date"].max().strftime("%Y-%m-%d")
                result = {
                    "stock_id": stock_id,
                    "fetched_rows": int(len(incoming)),
                    "written_rows": int(written_rows),
                    "latest_date": latest_date,
                }
            else:
                result = update_stock_price_csv(
                    stock_id,
                    data_dir,
                    start_date=start_date,
                    end_date=end_date,
                    token=token,
                )

            success_count += 1
            fetched_total += int(result["fetched_rows"])
            written_total += int(result.get("written_rows", result.get("fetched_rows", 0)))
            status["stocks"].append(
                {
                    "stock_id": stock_id,
                    "stock_name": stock_name,
                    "status": "ok",
                    "fetched_rows": result["fetched_rows"],
                    "written_rows": result.get("written_rows"),
                    "total_rows": result.get("total_rows"),
                    "latest_date": result["latest_date"],
                }
            )

            detail = f"fetched={result['fetched_rows']}"
            if target == "supabase":
                detail += f", upserted={result['written_rows']}"
            else:
                detail += f", total={result['total_rows']}"
            print(f"[{index}/{len(stock_pool)}] OK {label}: {detail}, latest={result['latest_date']}")
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
    status["fetched_rows"] = fetched_total
    status["written_rows"] = written_total
    status["status"] = "ok" if success_count > 0 and fail_count == 0 else "partial_failed"

    if target == "supabase":
        try:
            insert_update_log(
                config,
                {
                    "source": "FinMind",
                    "target": "supabase",
                    "started_at": started_at,
                    "finished_at": status["finished_at"],
                    "start_date": supabase_start_date,
                    "end_date": end_date,
                    "stock_count": len(stock_pool),
                    "success_count": success_count,
                    "fail_count": fail_count,
                    "fetched_rows": fetched_total,
                    "written_rows": written_total,
                    "status": status["status"],
                    "error": "" if fail_count == 0 else "One or more stock updates failed. See local status file.",
                },
            )
        except SupabaseWriteError as exc:
            print(f"WARN: failed to insert Supabase update log: {exc}")

    write_update_status(output_dir, status)
    return 0 if success_count > 0 and fail_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
