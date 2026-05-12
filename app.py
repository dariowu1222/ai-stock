import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from advisor.ai_advisor import build_stock_report, recommend_strategies
from advisor.report_writer import write_markdown_report
from backtest.engine import run_backtest
from backtest.metrics import calculate_backtest_metrics
from data.chip import get_chip_score
from data.finmind import update_stock_price_csv
from data.loader import (
    load_all_prices,
    load_all_prices_from_supabase,
    load_stock_pool,
    load_stock_pool_from_supabase,
)
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

BACKTEST_SUMMARY_LABELS = {
    "stock_id": "股票代號",
    "stock_name": "股票名稱",
    "trade_count": "交易次數",
    "win_rate": "勝率",
    "avg_return": "平均報酬",
    "max_drawdown": "最大回撤",
    "total_return": "總報酬",
}

TRADE_DETAIL_LABELS = {
    "stock_id": "股票代號",
    "stock_name": "股票名稱",
    "strategy_name": "策略代號",
    "signal_date": "訊號日",
    "entry_date": "進場日",
    "entry_price": "進場價",
    "exit_date": "出場日",
    "exit_price": "出場價",
    "holding_days": "持有天數",
    "gross_return": "未扣成本報酬",
    "net_return": "扣成本後報酬",
    "is_win": "是否獲利",
}

CANDIDATE_LABELS = {
    "stock_id": "股票代號",
    "stock_name": "股票名稱",
    "strategy_name": "策略代號",
    "strategy_display": "策略名稱",
    "signal_date": "訊號日期",
    "close": "收盤價",
    "volume": "成交量",
    "rsi14": "RSI14",
    "ma5": "MA5",
    "ma20": "MA20",
    "ma60": "MA60",
    "technical_score": "技術分數",
    "reason": "符合原因",
}


def load_config(path: str = "config.json") -> dict:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    return json.loads(config_path.read_text(encoding="utf-8"))


@st.cache_data(show_spinner="Loading Supabase market data...")
def load_market_data(config: dict) -> tuple[list[dict], dict[str, pd.DataFrame]]:
    if config.get("data_source") == "supabase":
        stock_pool = load_stock_pool_from_supabase(config)
        price_data = load_all_prices_from_supabase(config, stock_pool)
        return stock_pool, price_data

    stock_pool = load_stock_pool(config["stock_pool_file"])
    price_data = load_all_prices(config["data_dir"], stock_pool)
    return stock_pool, price_data


def ensure_output_dirs(output_dir: str) -> Path:
    base = Path(output_dir)
    (base / "reports").mkdir(parents=True, exist_ok=True)
    return base


def load_price_update_status(output_dir: str) -> dict | None:
    candidates = [
        Path(output_dir) / "bootstrap_stock_pool_status.json",
        Path(output_dir) / "price_update_status.json",
    ]
    statuses = []
    for path in candidates:
        if not path.exists():
            continue
        try:
            status = json.loads(path.read_text(encoding="utf-8-sig"))
            status["_status_file"] = path.name
            statuses.append(status)
        except Exception:
            continue
    if not statuses:
        return None
    return max(statuses, key=lambda item: item.get("finished_at") or item.get("started_at") or "")


def write_price_update_status(output_dir: str, status: dict) -> None:
    path = Path(output_dir) / "price_update_status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def format_percent(value: float | int | None) -> str:
    if value is None:
        return "N/A"
    return f"{float(value) * 100:.2f}%"


def localize_columns(df: pd.DataFrame, labels: dict[str, str]) -> pd.DataFrame:
    if df.empty:
        return df.rename(columns=labels)
    return df.rename(columns={column: labels.get(column, column) for column in df.columns})


def get_price_data_bounds(price_data: dict[str, pd.DataFrame]) -> tuple[date, date]:
    dates = []
    for df in price_data.values():
        if df.empty:
            continue
        parsed = pd.to_datetime(df["date"], errors="coerce").dropna()
        if not parsed.empty:
            dates.append(parsed.min().date())
            dates.append(parsed.max().date())

    today = date.today()
    if not dates:
        return today - timedelta(days=365), today
    return min(dates), max(dates)


def filter_price_data_by_date(
    price_data: dict[str, pd.DataFrame],
    start_date: date,
    end_date: date,
) -> dict[str, pd.DataFrame]:
    filtered = {}
    for stock_id, df in price_data.items():
        if df.empty:
            filtered[stock_id] = df.copy()
            continue
        dates = pd.to_datetime(df["date"], errors="coerce")
        mask = (dates.dt.date >= start_date) & (dates.dt.date <= end_date)
        filtered[stock_id] = df.loc[mask].sort_values("date").reset_index(drop=True)
    return filtered


def render_data_range_controls(price_data: dict[str, pd.DataFrame]) -> tuple[date, date]:
    min_date, max_date = get_price_data_bounds(price_data)
    default_start = max(min_date, max_date - timedelta(days=365))

    st.sidebar.header("資料區間")
    selected = st.sidebar.date_input(
        "分析與更新區間",
        value=(default_start, max_date),
        min_value=date(2010, 1, 1),
        max_value=date.today(),
    )
    if isinstance(selected, (tuple, list)) and len(selected) == 2:
        start_date, end_date = selected
    else:
        start_date = default_start
        end_date = max_date

    if start_date > end_date:
        start_date, end_date = end_date, start_date
    st.sidebar.caption("目前使用此區間做策略篩選、圖表與回測。")
    return start_date, end_date


def update_price_data_for_range(
    config: dict,
    stock_pool: list[dict],
    start_date: date,
    end_date: date,
) -> dict:
    output_dir = config.get("output_dir", "output")
    data_dir = config.get("data_dir", "price_data")
    sleep_seconds = float(config.get("finmind_request_sleep_seconds", 0.8))
    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = {
        "source": "FinMind",
        "started_at": started_at,
        "finished_at": "",
        "range_start": start_date.isoformat(),
        "range_end": end_date.isoformat(),
        "end_date": end_date.isoformat(),
        "success_count": 0,
        "fail_count": 0,
        "stocks": [],
        "status": "running",
    }
    write_price_update_status(output_dir, status)

    success_count = 0
    fail_count = 0
    for index, stock in enumerate(stock_pool, start=1):
        stock_id = str(stock.get("stock_id", "")).strip()
        stock_name = str(stock.get("stock_name", "")).strip()
        if not stock_id:
            continue
        try:
            result = update_stock_price_csv(
                stock_id,
                data_dir,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
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

        if index < len(stock_pool) and sleep_seconds > 0:
            time.sleep(sleep_seconds)

    status["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status["success_count"] = success_count
    status["fail_count"] = fail_count
    status["status"] = "ok" if success_count > 0 and fail_count == 0 else "partial_failed"
    write_price_update_status(output_dir, status)
    return status


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


def format_chart_number(value: float | int | None, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    number = float(value)
    if number.is_integer():
        return f"{number:,.0f}"
    return f"{number:,.{digits}f}"


def build_stock_name_map(stock_pool: list[dict]) -> dict[str, str]:
    return {
        str(stock.get("stock_id", "")).strip(): str(stock.get("stock_name", "")).strip()
        for stock in stock_pool
        if str(stock.get("stock_id", "")).strip()
    }


def build_available_stock_ids(stock_pool: list[dict], price_data: dict[str, pd.DataFrame]) -> list[str]:
    stock_ids = []
    for stock in stock_pool:
        stock_id = str(stock.get("stock_id", "")).strip()
        if stock_id and stock_id in price_data and not price_data[stock_id].empty:
            stock_ids.append(stock_id)
    return stock_ids


def get_default_chart_stock_id(available_stock_ids: list[str], ranked: pd.DataFrame) -> str | None:
    if not available_stock_ids:
        return None
    if not ranked.empty and "stock_id" in ranked.columns:
        for stock_id in ranked["stock_id"].astype(str):
            if stock_id in available_stock_ids:
                return stock_id
    return available_stock_ids[0]


def prepare_chart_data(df: pd.DataFrame) -> pd.DataFrame:
    chart_data = add_all_indicators(df)
    chart_data["date"] = pd.to_datetime(chart_data["date"], errors="coerce")
    chart_data = chart_data.dropna(subset=["date", "open", "high", "low", "close", "volume"])
    return chart_data.sort_values("date").reset_index(drop=True)


def build_price_volume_figure(
    chart_data: pd.DataFrame,
    stock_label: str,
    ma_columns: list[str],
    show_volume_ma: bool,
) -> go.Figure:
    volume_colors = [
        "#ef4444" if close_price >= open_price else "#22c55e"
        for open_price, close_price in zip(chart_data["open"], chart_data["close"])
    ]
    ma_colors = {
        "ma5": "#f59e0b",
        "ma10": "#38bdf8",
        "ma20": "#a78bfa",
        "ma60": "#f97316",
    }
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.72, 0.28],
        vertical_spacing=0.04,
        specs=[[{}], [{}]],
    )
    fig.add_trace(
        go.Candlestick(
            x=chart_data["date"],
            open=chart_data["open"],
            high=chart_data["high"],
            low=chart_data["low"],
            close=chart_data["close"],
            name="K線",
            increasing_line_color="#ef4444",
            increasing_fillcolor="#ef4444",
            decreasing_line_color="#22c55e",
            decreasing_fillcolor="#22c55e",
        ),
        row=1,
        col=1,
    )
    for ma_column in ma_columns:
        if ma_column in chart_data.columns:
            fig.add_trace(
                go.Scatter(
                    x=chart_data["date"],
                    y=chart_data[ma_column],
                    mode="lines",
                    name=ma_column.upper(),
                    line={"color": ma_colors.get(ma_column, "#e5e7eb"), "width": 1.6},
                ),
                row=1,
                col=1,
            )
    fig.add_trace(
        go.Bar(
            x=chart_data["date"],
            y=chart_data["volume"],
            name="成交量",
            marker_color=volume_colors,
            opacity=0.65,
        ),
        row=2,
        col=1,
    )
    if show_volume_ma:
        for column, color in [("avg_volume_5", "#fbbf24"), ("avg_volume_20", "#60a5fa")]:
            if column in chart_data.columns:
                fig.add_trace(
                    go.Scatter(
                        x=chart_data["date"],
                        y=chart_data[column],
                        mode="lines",
                        name=column.replace("avg_volume_", "量MA"),
                        line={"color": color, "width": 1.4},
                    ),
                    row=2,
                    col=1,
                )
    fig.update_layout(
        title=f"{stock_label} K線、均線、成交量",
        template="plotly_dark",
        height=660,
        margin={"l": 20, "r": 20, "t": 56, "b": 20},
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        xaxis_rangeslider_visible=False,
    )
    fig.update_yaxes(title_text="價格", row=1, col=1)
    fig.update_yaxes(title_text="成交量", row=2, col=1)
    return fig


def build_rsi_figure(chart_data: pd.DataFrame, stock_label: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=chart_data["date"],
            y=chart_data["rsi14"],
            mode="lines",
            name="RSI14",
            line={"color": "#38bdf8", "width": 2},
        )
    )
    fig.add_hline(y=70, line_dash="dash", line_color="#ef4444", annotation_text="偏熱 70")
    fig.add_hline(y=30, line_dash="dash", line_color="#22c55e", annotation_text="偏冷 30")
    fig.update_layout(
        title=f"{stock_label} RSI",
        template="plotly_dark",
        height=320,
        margin={"l": 20, "r": 20, "t": 48, "b": 20},
        hovermode="x unified",
    )
    fig.update_yaxes(range=[0, 100])
    return fig


def build_macd_figure(chart_data: pd.DataFrame, stock_label: str) -> go.Figure:
    hist_colors = ["#ef4444" if value >= 0 else "#22c55e" for value in chart_data["macd_hist"].fillna(0)]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=chart_data["date"], y=chart_data["macd_hist"], name="MACD柱", marker_color=hist_colors))
    fig.add_trace(
        go.Scatter(
            x=chart_data["date"],
            y=chart_data["macd"],
            mode="lines",
            name="MACD",
            line={"color": "#f59e0b", "width": 1.8},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=chart_data["date"],
            y=chart_data["macd_signal"],
            mode="lines",
            name="Signal",
            line={"color": "#60a5fa", "width": 1.8},
        )
    )
    fig.update_layout(
        title=f"{stock_label} MACD",
        template="plotly_dark",
        height=320,
        margin={"l": 20, "r": 20, "t": 48, "b": 20},
        hovermode="x unified",
        legend={"orientation": "h"},
    )
    return fig


def build_kd_figure(chart_data: pd.DataFrame, stock_label: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=chart_data["date"],
            y=chart_data["k"],
            mode="lines",
            name="K值",
            line={"color": "#f59e0b", "width": 1.8},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=chart_data["date"],
            y=chart_data["d"],
            mode="lines",
            name="D值",
            line={"color": "#a78bfa", "width": 1.8},
        )
    )
    fig.add_hline(y=80, line_dash="dash", line_color="#ef4444", annotation_text="偏熱 80")
    fig.add_hline(y=20, line_dash="dash", line_color="#22c55e", annotation_text="偏冷 20")
    fig.update_layout(
        title=f"{stock_label} KD",
        template="plotly_dark",
        height=320,
        margin={"l": 20, "r": 20, "t": 48, "b": 20},
        hovermode="x unified",
        legend={"orientation": "h"},
    )
    fig.update_yaxes(range=[0, 100])
    return fig


def render_stock_charts(
    price_data: dict[str, pd.DataFrame],
    stock_pool: list[dict],
    ranked: pd.DataFrame,
) -> None:
    st.subheader("股票技術圖表")
    available_stock_ids = build_available_stock_ids(stock_pool, price_data)
    if not available_stock_ids:
        st.info("目前沒有可畫圖的股價資料。請先建立股票池並完成至少一檔股價資料下載。")
        return

    name_by_id = build_stock_name_map(stock_pool)
    default_stock_id = get_default_chart_stock_id(available_stock_ids, ranked)
    default_index = available_stock_ids.index(default_stock_id) if default_stock_id else 0

    control_col1, control_col2, control_col3 = st.columns([2, 2, 1])
    selected_stock_id = control_col1.selectbox(
        "選擇股票",
        available_stock_ids,
        index=default_index,
        format_func=lambda stock_id: f"{stock_id} {name_by_id.get(stock_id, '')}".strip(),
    )
    ma_columns = control_col2.multiselect(
        "顯示均線",
        ["ma5", "ma10", "ma20", "ma60"],
        default=["ma5", "ma20", "ma60"],
        format_func=lambda column: column.upper(),
    )
    show_volume_ma = control_col3.checkbox("量均線", value=True)

    stock_label = f"{selected_stock_id} {name_by_id.get(selected_stock_id, '')}".strip()
    chart_data = prepare_chart_data(price_data[selected_stock_id])
    if chart_data.empty:
        st.info("這檔股票在目前資料區間內沒有可畫圖資料。")
        return

    latest = chart_data.iloc[-1]
    previous_close = chart_data["close"].shift(1).iloc[-1]
    close_delta = None if pd.isna(previous_close) else latest["close"] - previous_close
    close_delta_pct = None if pd.isna(previous_close) or previous_close == 0 else close_delta / previous_close

    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
    metric_col1.metric(
        "最新收盤價",
        format_chart_number(latest["close"]),
        None if close_delta is None else f"{close_delta:+.2f} ({close_delta_pct:+.2%})",
    )
    metric_col2.metric("最新成交量", format_chart_number(latest["volume"], digits=0))
    metric_col3.metric("RSI14", format_chart_number(latest.get("rsi14"), digits=2))
    metric_col4.metric("圖表資料筆數", len(chart_data))
    st.caption(f"圖表資料區間：{chart_data['date'].min().date()} 至 {chart_data['date'].max().date()}")

    st.plotly_chart(
        build_price_volume_figure(chart_data, stock_label, ma_columns, show_volume_ma),
        use_container_width=True,
    )
    indicator_col1, indicator_col2 = st.columns(2)
    with indicator_col1:
        st.plotly_chart(build_rsi_figure(chart_data, stock_label), use_container_width=True)
    with indicator_col2:
        st.plotly_chart(build_macd_figure(chart_data, stock_label), use_container_width=True)
    st.plotly_chart(build_kd_figure(chart_data, stock_label), use_container_width=True)


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
    st.caption("第一階段：Supabase 日 K 資料、策略篩選、固定持有天數回測、Markdown 報告。不提供真實下單。")

    try:
        config = load_config()
        output_dir = ensure_output_dirs(config["output_dir"])
        update_status = load_price_update_status(config["output_dir"])
        stock_pool, price_data = load_market_data(config)
    except Exception as exc:
        st.error(f"初始化失敗：{exc}")
        return

    if config.get("enable_live_trading") is True:
        st.error("MVP 階段禁止 live trading；畫面已忽略 enable_live_trading=true。")
        config["enable_live_trading"] = False

    market_context = get_market_context()
    recommendations = recommend_strategies(market_context)
    default_strategy = "ma_bullish"
    selected_start_date, selected_end_date = render_data_range_controls(price_data)
    if config.get("data_source") == "supabase":
        st.sidebar.caption("Data source: Supabase")
    elif st.sidebar.button("更新此區間股價", type="primary"):
        with st.spinner("正在向 FinMind 更新指定日期區間..."):
            update_status = update_price_data_for_range(
                config,
                stock_pool,
                selected_start_date,
                selected_end_date,
            )
            price_data = load_all_prices(config["data_dir"], stock_pool)
        if int(update_status.get("fail_count", 0)) == 0:
            st.sidebar.success("區間資料更新完成")
        else:
            st.sidebar.warning("部分股票更新失敗，請查看資料載入狀態")

    price_data = filter_price_data_by_date(price_data, selected_start_date, selected_end_date)
    strategy_name, params, top_n, holding_days = render_strategy_controls(default_strategy)

    render_market_context(market_context)
    render_recommendations(recommendations)

    st.divider()
    st.subheader("資料載入狀態")
    data_status = build_price_data_status(stock_pool, price_data)
    latest_dates = [value for value in data_status.get("latest_date", []) if value]
    latest_date = max(latest_dates) if latest_dates else "N/A"
    loaded_stock_count = int((data_status["rows"] > 0).sum()) if "rows" in data_status else 0
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("股票池", len(stock_pool))
    col2.metric("已載入股票資料", loaded_stock_count)
    col3.metric("最新資料日", latest_date)
    col4.metric("Live Trading", "Disabled")
    st.caption(f"目前分析區間：{selected_start_date.isoformat()} 至 {selected_end_date.isoformat()}")
    if config.get("data_source") == "supabase":
        st.success("資料來源：Supabase；股票池與日 K 皆由遠端資料庫載入。")
    elif update_status:
        status_text = update_status.get("status", "unknown")
        finished_at = update_status.get("finished_at") or update_status.get("started_at") or "N/A"
        success_count = update_status.get("success_count", 0)
        fail_count = update_status.get("fail_count", 0)
        no_data_count = update_status.get("no_data_count", 0)
        skipped_count = update_status.get("skipped_count", 0)
        st.success(
            f"最後更新時間：{finished_at}；來源：{update_status.get('source', 'N/A')}；"
            f"狀態：{status_text}；成功 {success_count} 檔、無資料 {no_data_count} 檔、"
            f"跳過 {skipped_count} 檔、失敗 {fail_count} 檔。"
        )
    else:
        st.warning("尚未找到股價更新紀錄；請重新啟動系統讓 FinMind 更新流程執行。")
    with st.expander("每檔資料狀態", expanded=False):
        st.dataframe(data_status, width="stretch")

    if not price_data:
        st.warning("沒有可用股價資料，請確認資料來源設定與 Supabase 連線。")
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

    tab_screen, tab_chart, tab_backtest, tab_report, tab_limits = st.tabs(["候選股", "圖表", "回測", "報告", "限制"])

    with tab_screen:
        st.subheader("Top N 候選股")
        if ranked.empty:
            st.info("最新一日沒有股票符合目前策略條件。可在左側切換策略或調整參數。")
        else:
            st.dataframe(localize_columns(ranked, CANDIDATE_LABELS), width="stretch")
        st.caption(f"已匯出：{screener_path}")

    with tab_chart:
        render_stock_charts(price_data, stock_pool, ranked)

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
            st.dataframe(localize_columns(pd.DataFrame(metric_rows), BACKTEST_SUMMARY_LABELS), width="stretch")
            with st.expander("交易明細"):
                st.dataframe(
                    localize_columns(trades, TRADE_DETAIL_LABELS),
                    width="stretch",
                    height=420,
                )
                st.caption(f"交易明細總筆數：{len(trades)}")
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
