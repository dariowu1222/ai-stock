import json
from pathlib import Path

import pandas as pd
import streamlit as st

from advisor.ai_advisor import build_stock_report, recommend_strategies
from advisor.report_writer import write_markdown_report
from backtest.engine import run_backtest
from backtest.metrics import calculate_backtest_metrics
from data.chip import get_chip_score
from data.loader import load_all_prices, load_stock_pool
from data.market import get_market_context
from screener.ranking import rank_screening_result
from screener.screener import screen_stocks
from strategy.indicators import add_all_indicators
from strategy.signal_engine import generate_signal
from strategy.templates import list_strategy_templates


BACKTEST_EXPORT_COLUMNS = [
    "stock_id",
    "stock_name",
    "strategy_name",
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


def load_config(path: str = "config.json") -> dict:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    return json.loads(config_path.read_text(encoding="utf-8"))


def ensure_output_dirs(output_dir: str) -> Path:
    base = Path(output_dir)
    (base / "reports").mkdir(parents=True, exist_ok=True)
    return base


def load_price_update_status(output_dir: str) -> dict | None:
    path = Path(output_dir) / "price_update_status.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def format_percent(value: float | int | None) -> str:
    if value is None:
        return "N/A"
    return f"{float(value) * 100:.2f}%"


def build_price_data_status(stock_pool: list[dict], price_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for stock in stock_pool:
        stock_id = str(stock.get("stock_id", "")).strip()
        df = price_data.get(stock_id)
        if df is None or df.empty:
            rows.append(
                {
                    "stock_id": stock_id,
                    "stock_name": stock.get("stock_name", ""),
                    "rows": 0,
                    "start_date": "",
                    "latest_date": "",
                }
            )
            continue

        dates = pd.to_datetime(df["date"], errors="coerce")
        rows.append(
            {
                "stock_id": stock_id,
                "stock_name": stock.get("stock_name", ""),
                "rows": len(df),
                "start_date": dates.min().strftime("%Y-%m-%d"),
                "latest_date": dates.max().strftime("%Y-%m-%d"),
            }
        )
    return pd.DataFrame(rows)


def render_market_context(market_context: dict) -> None:
    st.subheader("市場情境")
    col1, col2, col3 = st.columns(3)
    col1.metric("市場型態", market_context.get("market_regime", "N/A"))
    col2.metric("風險等級", market_context.get("risk_level", "N/A"))
    col3.metric("市場分數", market_context.get("market_score", "N/A"))
    st.info(market_context.get("summary", ""))


def render_recommendations(recommendations: list[dict]) -> None:
    st.subheader("AI 推薦策略（規則式 MVP）")
    for item in recommendations:
        with st.container(border=True):
            st.markdown(f"**{item['display_name']}**")
            st.caption(item.get("reason", ""))
            st.json(item.get("params", {}), expanded=False)


def render_strategy_controls(default_strategy: str) -> tuple[str, dict, int, int]:
    templates = list_strategy_templates()
    strategy_names = [item["strategy_name"] for item in templates]
    display_by_name = {item["strategy_name"]: item["display_name"] for item in templates}
    template_by_name = {item["strategy_name"]: item for item in templates}
    default_index = strategy_names.index(default_strategy) if default_strategy in strategy_names else 0

    st.sidebar.header("策略設定")
    strategy_name = st.sidebar.selectbox(
        "選擇策略",
        strategy_names,
        index=default_index,
        format_func=lambda name: display_by_name[name],
    )
    st.sidebar.caption(template_by_name[strategy_name]["description"])

    params = {}
    defaults = template_by_name[strategy_name].get("default_params", {})
    for key, value in defaults.items():
        params[key] = st.sidebar.number_input(
            key,
            value=float(value),
            min_value=0.0,
            step=0.05 if isinstance(value, float) else 1.0,
        )

    top_n = st.sidebar.number_input("Top N", value=10, min_value=1, max_value=100, step=1)
    holding_days = st.sidebar.number_input("回測持有天數", value=5, min_value=1, max_value=60, step=1)
    return strategy_name, params, int(top_n), int(holding_days)


def run_candidate_backtests(
    ranked: pd.DataFrame,
    price_data: dict[str, pd.DataFrame],
    strategy_name: str,
    params: dict,
    holding_days: int,
    trade_cost_rate: float,
) -> tuple[pd.DataFrame, dict[str, dict]]:
    trade_frames = []
    metrics_by_stock = {}

    for _, row in ranked.iterrows():
        stock_id = str(row["stock_id"])
        data = add_all_indicators(price_data[stock_id])
        signal = generate_signal(data, strategy_name, params)
        trades = run_backtest(data, signal, holding_days=holding_days, trade_cost_rate=trade_cost_rate)
        metrics = calculate_backtest_metrics(trades)
        metrics_by_stock[stock_id] = metrics

        if not trades.empty:
            trades = trades.copy()
            trades.insert(0, "stock_id", stock_id)
            trades.insert(1, "stock_name", row["stock_name"])
            trades.insert(2, "strategy_name", strategy_name)
            trade_frames.append(trades)

    if not trade_frames:
        return pd.DataFrame(columns=BACKTEST_EXPORT_COLUMNS), metrics_by_stock
    return pd.concat(trade_frames, ignore_index=True), metrics_by_stock


def main() -> None:
    st.set_page_config(page_title="AI 台股策略顧問 MVP", layout="wide")
    st.title("AI 台股策略顧問系統 MVP")
    st.caption("第一階段：FinMind 日 K 更新、本地 CSV 快取、策略篩選、固定持有天數回測、Markdown 報告。不提供真實下單。")

    try:
        config = load_config()
        output_dir = ensure_output_dirs(config["output_dir"])
        update_status = load_price_update_status(config["output_dir"])
        stock_pool = load_stock_pool(config["stock_pool_file"])
        price_data = load_all_prices(config["data_dir"], stock_pool)
    except Exception as exc:
        st.error(f"初始化失敗：{exc}")
        return

    if config.get("enable_live_trading") is True:
        st.error("MVP 階段禁止 live trading；畫面已忽略 enable_live_trading=true。")
        config["enable_live_trading"] = False

    market_context = get_market_context()
    recommendations = recommend_strategies(market_context)
    default_strategy = "ma_bullish"
    strategy_name, params, top_n, holding_days = render_strategy_controls(default_strategy)

    render_market_context(market_context)
    render_recommendations(recommendations)

    st.divider()
    st.subheader("資料載入狀態")
    data_status = build_price_data_status(stock_pool, price_data)
    latest_dates = [value for value in data_status.get("latest_date", []) if value]
    latest_date = max(latest_dates) if latest_dates else "N/A"
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("股票池", len(stock_pool))
    col2.metric("已載入 CSV", len(price_data))
    col3.metric("最新資料日", latest_date)
    col4.metric("Live Trading", "Disabled")
    if update_status:
        status_text = update_status.get("status", "unknown")
        finished_at = update_status.get("finished_at") or update_status.get("started_at") or "N/A"
        success_count = update_status.get("success_count", 0)
        fail_count = update_status.get("fail_count", 0)
        st.success(
            f"最後更新時間：{finished_at}；來源：{update_status.get('source', 'N/A')}；"
            f"狀態：{status_text}；成功 {success_count} 檔、失敗 {fail_count} 檔。"
        )
    else:
        st.warning("尚未找到股價更新紀錄；請重新啟動系統讓 FinMind 更新流程執行。")
    with st.expander("每檔資料狀態", expanded=False):
        st.dataframe(data_status, width="stretch")

    if not price_data:
        st.warning("沒有可用 CSV，請確認啟動時的 FinMind 更新是否成功，或檢查 data_dir 設定。")
        return

    ranked = rank_screening_result(
        screen_stocks(price_data, stock_pool, strategy_name, params),
        top_n=top_n,
    )
    screener_path = output_dir / "screener_result.csv"
    ranked.to_csv(screener_path, index=False, encoding="utf-8-sig")

    trades, metrics_by_stock = run_candidate_backtests(
        ranked,
        price_data,
        strategy_name,
        params,
        holding_days,
        float(config["trade_cost_rate"]),
    )
    backtest_path = output_dir / "backtest_result.csv"
    trades.to_csv(backtest_path, index=False, encoding="utf-8-sig")

    tab_screen, tab_backtest, tab_report, tab_limits = st.tabs(["候選股", "回測", "報告", "限制"])

    with tab_screen:
        st.subheader("Top N 候選股")
        if ranked.empty:
            st.info("最新一日沒有股票符合目前策略條件。可在左側切換策略或調整參數。")
        else:
            st.dataframe(ranked, width="stretch")
        st.caption(f"已匯出：{screener_path}")

    with tab_backtest:
        st.subheader("固定持有天數回測")
        if ranked.empty:
            st.info("沒有候選股，因此未產生回測結果。")
        else:
            metric_rows = []
            for _, row in ranked.iterrows():
                stock_id = str(row["stock_id"])
                metrics = metrics_by_stock.get(stock_id, {})
                metric_rows.append(
                    {
                        "stock_id": stock_id,
                        "stock_name": row["stock_name"],
                        "trade_count": metrics.get("trade_count", 0),
                        "win_rate": format_percent(metrics.get("win_rate", 0)),
                        "avg_return": format_percent(metrics.get("avg_return", 0)),
                        "max_drawdown": format_percent(metrics.get("max_drawdown", 0)),
                        "total_return": format_percent(metrics.get("total_return", 0)),
                    }
                )
            st.dataframe(pd.DataFrame(metric_rows), width="stretch")
            with st.expander("交易明細"):
                st.dataframe(trades, width="stretch")
        st.caption(f"已匯出：{backtest_path}")

    with tab_report:
        st.subheader("Markdown 個股報告")
        if ranked.empty:
            st.info("沒有候選股可產生報告。")
        else:
            report_paths = []
            for _, row in ranked.iterrows():
                stock_id = str(row["stock_id"])
                report = build_stock_report(
                    row.to_dict(),
                    metrics_by_stock.get(stock_id),
                    market_context,
                    get_chip_score(stock_id),
                )
                report_path = output_dir / "reports" / f"{stock_id}_{strategy_name}.md"
                write_markdown_report(report, str(report_path))
                report_paths.append(str(report_path))
            st.write("已產出報告：")
            for report_path in report_paths:
                st.code(report_path)

    with tab_limits:
        st.subheader("MVP 風險控管")
        st.write(
            "- 不提供真實下單按鈕。\n"
            "- 不提供 live mode 切換。\n"
            "- 不呼叫 Shioaji。\n"
            "- 策略、回測與報告只作為研究與決策輔助，不構成投資建議。\n"
            "- 回測採下一交易日開盤進場，固定持有天數後以收盤價出場，並扣交易成本。"
        )


if __name__ == "__main__":
    main()
