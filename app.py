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
from reports import generate_bull_bear, generate_comp_sheet, generate_tear_sheet
from reports.base import (
    AUDIENCE_LABELS,
    AUDIENCE_PRO,
    AUDIENCE_RETAIL,
    AUDIENCE_SELF_TRADE,
)
from screener.ranking import rank_screening_result
from screener.screener import screen_stocks
from strategy.indicators import add_all_indicators, add_high_low_breakout, add_rsi, add_volume_averages
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


FILTER_RESULT_LABELS = {
    "stock_id": "股票代號",
    "stock_name": "股票名稱",
    "market": "市場別",
    "industry_category": "產業類別",
    "latest_date": "最新資料日",
    "rows_count": "K棒數",
    "current_strategy_signal": "目前策略訊號",
    "close": "收盤價",
    "day_return": "日漲跌幅",
    "volume": "成交量",
    "volume_ratio_20": "量比20日",
    "rsi5": "RSI5",
    "rsi9": "RSI9",
    "rsi14": "RSI14",
    "rsi20": "RSI20",
    "ma5": "MA5",
    "ma20": "MA20",
    "ma60": "MA60",
    "bias20": "20日乖離率",
    "macd_hist": "MACD柱",
    "k": "K值",
    "d": "D值",
    "atr_pct": "ATR百分比",
    "volatility_20": "20日波動率",
    "return_20d": "20日報酬率",
    "breakout_20": "突破20日高",
    "bullish_ma_order": "均線多頭",
}


FILTER_DEFINITIONS = [
    {"key": "rows_count", "label": "可用K棒數", "category": "資料品質", "help": "目前分析區間內，該股票可用的日K資料筆數。"},
    {"key": "rank", "label": "股票池排名", "category": "股票池", "help": "Supabase 股票池中的排序，數字越小代表排序越前面。"},
    {"key": "strength_score", "label": "強度分數", "category": "股票池", "help": "股票池預先計算的綜合強度分數。"},
    {"key": "popularity_weight", "label": "熱門權重", "category": "股票池", "help": "股票池預先給定的熱門程度或關注權重。"},
    {"key": "close", "label": "最新收盤價", "category": "價格", "help": "最新交易日的收盤價格。"},
    {"key": "open", "label": "最新開盤價", "category": "價格", "help": "最新交易日的開盤價格。"},
    {"key": "high", "label": "最新最高價", "category": "價格", "help": "最新交易日盤中最高價格。"},
    {"key": "low", "label": "最新最低價", "category": "價格", "help": "最新交易日盤中最低價格。"},
    {"key": "day_return", "label": "日漲跌幅", "category": "價格", "unit": "pct", "help": "最新收盤價相對前一交易日收盤價的漲跌百分比。"},
    {"key": "gap_pct", "label": "開盤跳空幅度", "category": "價格", "unit": "pct", "help": "最新開盤價相對前一交易日收盤價的差距百分比。"},
    {"key": "amplitude_pct", "label": "振幅", "category": "價格", "unit": "pct", "help": "當日最高價與最低價相對前一日收盤價的波動幅度。"},
    {"key": "body_pct", "label": "K棒實體幅度", "category": "K線", "unit": "pct", "help": "收盤價與開盤價的差距百分比，用來衡量當日實體大小。"},
    {"key": "upper_shadow_pct", "label": "上影線幅度", "category": "K線", "unit": "pct", "help": "最高價高於開收盤較高者的幅度，常用來觀察上檔賣壓。"},
    {"key": "lower_shadow_pct", "label": "下影線幅度", "category": "K線", "unit": "pct", "help": "開收盤較低者高於最低價的幅度，常用來觀察低檔承接。"},
    {"key": "volume", "label": "最新成交量", "category": "量能", "help": "最新交易日成交股數。"},
    {"key": "avg_volume_5", "label": "5日均量", "category": "量能", "help": "最近5個交易日平均成交量。"},
    {"key": "avg_volume_20", "label": "20日均量", "category": "量能", "help": "最近20個交易日平均成交量。"},
    {"key": "avg_volume_60", "label": "60日均量", "category": "量能", "help": "最近60個交易日平均成交量。"},
    {"key": "volume_ratio_5", "label": "量比5日", "category": "量能", "help": "最新成交量除以5日均量，衡量短線放量程度。"},
    {"key": "volume_ratio_20", "label": "量比20日", "category": "量能", "help": "最新成交量除以20日均量，衡量是否明顯放量。"},
    {"key": "volume_change_pct", "label": "成交量變化率", "category": "量能", "unit": "pct", "help": "最新成交量相對前一交易日成交量的變化百分比。"},
    {"key": "return_1d", "label": "1日報酬率", "category": "報酬", "unit": "pct", "help": "最新收盤價相對前一交易日收盤價的報酬率。"},
    {"key": "return_5d", "label": "5日報酬率", "category": "報酬", "unit": "pct", "help": "最新收盤價相對5個交易日前收盤價的報酬率。"},
    {"key": "return_10d", "label": "10日報酬率", "category": "報酬", "unit": "pct", "help": "最新收盤價相對10個交易日前收盤價的報酬率。"},
    {"key": "return_20d", "label": "20日報酬率", "category": "報酬", "unit": "pct", "help": "最新收盤價相對20個交易日前收盤價的報酬率。"},
    {"key": "return_60d", "label": "60日報酬率", "category": "報酬", "unit": "pct", "help": "最新收盤價相對60個交易日前收盤價的報酬率。"},
    {"key": "ma5", "label": "MA5", "category": "均線", "help": "最近5個交易日收盤價移動平均線。"},
    {"key": "ma10", "label": "MA10", "category": "均線", "help": "最近10個交易日收盤價移動平均線。"},
    {"key": "ma20", "label": "MA20", "category": "均線", "help": "最近20個交易日收盤價移動平均線。"},
    {"key": "ma60", "label": "MA60", "category": "均線", "help": "最近60個交易日收盤價移動平均線。"},
    {"key": "ma20_slope", "label": "MA20斜率", "category": "均線", "unit": "pct", "help": "MA20相對前一日的變化百分比，用來觀察中短期趨勢方向。"},
    {"key": "bias5", "label": "5日乖離率", "category": "乖離", "unit": "pct", "help": "收盤價偏離MA5的百分比。"},
    {"key": "bias20", "label": "20日乖離率", "category": "乖離", "unit": "pct", "help": "收盤價偏離MA20的百分比。"},
    {"key": "bias60", "label": "60日乖離率", "category": "乖離", "unit": "pct", "help": "收盤價偏離MA60的百分比。"},
    {"key": "rsi5", "label": "RSI5", "category": "RSI", "help": "5日RSI，反映很短線買賣力道，數值越高越偏熱。"},
    {"key": "rsi9", "label": "RSI9", "category": "RSI", "help": "9日RSI，常用於短線動能判斷。"},
    {"key": "rsi14", "label": "RSI14", "category": "RSI", "help": "14日RSI，常用於超買超賣判斷。"},
    {"key": "rsi20", "label": "RSI20", "category": "RSI", "help": "20日RSI，反映較平滑的中短期動能。"},
    {"key": "macd", "label": "MACD值", "category": "MACD", "help": "快慢EMA差值，衡量趨勢動能。"},
    {"key": "macd_signal", "label": "MACD Signal", "category": "MACD", "help": "MACD訊號線，用於判斷動能轉折。"},
    {"key": "macd_hist", "label": "MACD Histogram", "category": "MACD", "help": "MACD與Signal的差距，柱狀體由負轉正常視為動能改善。"},
    {"key": "k", "label": "K值", "category": "KD", "help": "KD指標中的快速線，反映短線相對位置。"},
    {"key": "d", "label": "D值", "category": "KD", "help": "KD指標中的慢速線，較平滑地反映短線位置。"},
    {"key": "rsv", "label": "RSV", "category": "KD", "help": "目前收盤價在指定區間高低價中的相對位置。"},
    {"key": "high_20", "label": "前20日高點", "category": "突破", "help": "不含最新交易日的前20日最高價。"},
    {"key": "high_60", "label": "前60日高點", "category": "突破", "help": "不含最新交易日的前60日最高價。"},
    {"key": "distance_from_20d_high", "label": "距離20日高點", "category": "突破", "unit": "pct", "help": "收盤價距離前20日高點的百分比。"},
    {"key": "distance_from_60d_high", "label": "距離60日高點", "category": "突破", "unit": "pct", "help": "收盤價距離前60日高點的百分比。"},
    {"key": "atr14", "label": "ATR14", "category": "風險", "help": "14日平均真實波幅，衡量價格波動程度。"},
    {"key": "atr_pct", "label": "ATR百分比", "category": "風險", "unit": "pct", "help": "ATR14除以收盤價，方便比較不同股價股票的波動。"},
    {"key": "volatility_20", "label": "20日波動率", "category": "風險", "unit": "pct", "help": "最近20日報酬率標準差，衡量短期風險。"},
]


BOOLEAN_FILTER_DEFINITIONS = [
    {"key": "current_strategy_signal", "label": "符合目前策略訊號", "help": "是否在最新交易日符合左側目前選擇的策略與參數。"},
    {"key": "is_red_k", "label": "紅K", "help": "收盤價高於或等於開盤價。"},
    {"key": "price_above_ma5", "label": "收盤站上MA5", "help": "最新收盤價是否高於MA5。"},
    {"key": "price_above_ma20", "label": "收盤站上MA20", "help": "最新收盤價是否高於MA20。"},
    {"key": "price_above_ma60", "label": "收盤站上MA60", "help": "最新收盤價是否高於MA60。"},
    {"key": "bullish_ma_order", "label": "均線多頭排列", "help": "MA5 > MA20 > MA60，代表中短期趨勢偏多。"},
    {"key": "bearish_ma_order", "label": "均線空頭排列", "help": "MA5 < MA20 < MA60，代表中短期趨勢偏弱。"},
    {"key": "macd_turn_positive", "label": "MACD翻正", "help": "MACD Histogram由負轉正。"},
    {"key": "k_above_d", "label": "K值高於D值", "help": "K值高於D值，代表短線動能偏強。"},
    {"key": "breakout_20", "label": "突破20日高", "help": "最新收盤價突破前20日最高價。"},
    {"key": "breakout_60", "label": "突破60日高", "help": "最新收盤價突破前60日最高價。"},
    {"key": "is_tech_focus", "label": "科技股焦點", "help": "股票池是否標記為科技主題或科技焦點股票。"},
]


FILTER_CATEGORY_ORDER = [
    "資料品質",
    "股票池",
    "價格",
    "K線",
    "量能",
    "報酬",
    "均線",
    "乖離",
    "RSI",
    "MACD",
    "KD",
    "突破",
    "風險",
]


QUERY_STRATEGY_EXAMPLES = [
    {
        "name": "量價突破",
        "source_strategy": "volume_breakout",
        "description": "偏向找出剛突破前高、成交量放大，但 RSI 尚未過熱的股票。",
        "boolean": {"breakout_20": True, "price_above_ma20": True},
        "numeric": {
            "volume_ratio_20": (1.5, None),
            "rsi14": (None, 80),
            "ma20_slope": (0, None),
        },
    },
    {
        "name": "回檔轉強",
        "source_strategy": "pullback_rebound",
        "description": "偏向找出中期趨勢仍向上，短線重新站回 MA5 且 RSI 回升的股票。",
        "boolean": {"price_above_ma5": True, "price_above_ma20": True},
        "numeric": {
            "rsi14": (35, 75),
            "volume_ratio_20": (1.05, None),
            "ma20_slope": (0, None),
            "bias20": (-0.08, 0.12),
        },
    },
    {
        "name": "超跌反彈",
        "source_strategy": "oversold_rebound",
        "description": "偏向找出 RSI 從低檔回升、MACD 動能改善，且價格重新站上短均的股票。",
        "boolean": {"price_above_ma5": True},
        "numeric": {
            "rsi14": (40, 65),
            "macd_hist": (0, None),
            "bias20": (-0.18, 0.03),
        },
    },
    {
        "name": "均線多頭",
        "source_strategy": "ma_bullish",
        "description": "偏向找出 MA5 > MA20 > MA60、價格站上短均且量能不弱的趨勢股。",
        "boolean": {"bullish_ma_order": True, "price_above_ma5": True},
        "numeric": {
            "volume_ratio_20": (1.0, None),
            "rsi14": (45, 80),
            "return_20d": (0, None),
        },
    },
    {
        "name": "MACD 翻正",
        "source_strategy": "macd_turn_positive",
        "description": "偏向找出 MACD Histogram 剛由負轉正，短線動能初步改善的股票。",
        "boolean": {"macd_turn_positive": True},
        "numeric": {
            "rsi14": (35, 75),
            "volume_ratio_20": (0.8, None),
        },
    },
]


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


def get_strategy_display_name(strategy_name: str) -> str:
    for template in list_strategy_templates():
        if template["strategy_name"] == strategy_name:
            return template["display_name"]
    return strategy_name


def safe_ratio(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if numerator is None or denominator is None or pd.isna(numerator) or pd.isna(denominator):
        return None
    denominator = float(denominator)
    if denominator == 0:
        return None
    return float(numerator) / denominator


def pct_change_from(current: float | int | None, base: float | int | None) -> float | None:
    ratio = safe_ratio(current, base)
    if ratio is None:
        return None
    return ratio - 1


def latest_value(data: pd.DataFrame, column: str) -> float | None:
    if column not in data.columns or data.empty:
        return None
    value = data[column].iloc[-1]
    if pd.isna(value):
        return None
    return float(value)


def historical_return(data: pd.DataFrame, window: int) -> float | None:
    if len(data) <= window:
        return None
    return pct_change_from(data["close"].iloc[-1], data["close"].shift(window).iloc[-1])


def build_query_universe(
    price_data: dict[str, pd.DataFrame],
    stock_pool: list[dict],
    strategy_name: str,
    params: dict,
) -> pd.DataFrame:
    rows = []
    for stock in stock_pool:
        stock_id = str(stock.get("stock_id", "")).strip()
        df = price_data.get(stock_id)
        if not stock_id or df is None or df.empty:
            continue

        data = add_all_indicators(df)
        data = add_volume_averages(data, [5, 20, 60])
        for window in [5, 9, 20]:
            data = add_rsi(data, window)
        data = add_high_low_breakout(data, 60)
        data["ma20_slope"] = data["ma20"].pct_change()
        for window in [5, 20, 60]:
            ma_column = f"ma{window}"
            data[f"bias{window}"] = (data["close"] - data[ma_column]) / data[ma_column]
        data["volatility_20"] = data["daily_return"].rolling(window=20).std()

        data = data.dropna(subset=["date", "open", "high", "low", "close", "volume"])
        if data.empty:
            continue

        latest = data.iloc[-1]
        previous = data.iloc[-2] if len(data) >= 2 else None
        previous_close = None if previous is None else previous["close"]
        previous_volume = None if previous is None else previous["volume"]
        signal = generate_signal(data, strategy_name, params)
        current_strategy_signal = bool(signal.iloc[-1]) if not signal.empty else False

        close = latest["close"]
        open_price = latest["open"]
        high = latest["high"]
        low = latest["low"]
        avg_volume_5 = latest_value(data, "avg_volume_5")
        avg_volume_20 = latest_value(data, "avg_volume_20")
        high_20 = latest_value(data, "high_20")
        high_60 = latest_value(data, "high_60")
        atr14 = latest_value(data, "atr14")

        row = {
            "stock_id": stock_id,
            "stock_name": stock.get("stock_name", ""),
            "market": stock.get("market", ""),
            "industry_category": stock.get("industry_category", ""),
            "rank": stock.get("rank"),
            "strength_score": stock.get("strength_score"),
            "is_tech_focus": stock.get("is_tech_focus"),
            "popularity_weight": stock.get("popularity_weight"),
            "theme_tags": stock.get("theme_tags", ""),
            "latest_date": pd.to_datetime(latest["date"]).strftime("%Y-%m-%d"),
            "rows_count": len(data),
            "current_strategy_signal": current_strategy_signal,
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": latest["volume"],
            "day_return": pct_change_from(close, previous_close),
            "gap_pct": pct_change_from(open_price, previous_close),
            "amplitude_pct": safe_ratio(high - low, previous_close),
            "body_pct": safe_ratio(abs(close - open_price), open_price),
            "upper_shadow_pct": safe_ratio(high - max(open_price, close), open_price),
            "lower_shadow_pct": safe_ratio(min(open_price, close) - low, open_price),
            "is_red_k": close >= open_price,
            "avg_volume_5": avg_volume_5,
            "avg_volume_20": avg_volume_20,
            "avg_volume_60": latest_value(data, "avg_volume_60"),
            "volume_ratio_5": safe_ratio(latest["volume"], avg_volume_5),
            "volume_ratio_20": safe_ratio(latest["volume"], avg_volume_20),
            "volume_change_pct": pct_change_from(latest["volume"], previous_volume),
            "return_1d": pct_change_from(close, previous_close),
            "return_5d": historical_return(data, 5),
            "return_10d": historical_return(data, 10),
            "return_20d": historical_return(data, 20),
            "return_60d": historical_return(data, 60),
            "ma5": latest_value(data, "ma5"),
            "ma10": latest_value(data, "ma10"),
            "ma20": latest_value(data, "ma20"),
            "ma60": latest_value(data, "ma60"),
            "ma20_slope": latest_value(data, "ma20_slope"),
            "bias5": latest_value(data, "bias5"),
            "bias20": latest_value(data, "bias20"),
            "bias60": latest_value(data, "bias60"),
            "rsi5": latest_value(data, "rsi5"),
            "rsi9": latest_value(data, "rsi9"),
            "rsi14": latest_value(data, "rsi14"),
            "rsi20": latest_value(data, "rsi20"),
            "macd": latest_value(data, "macd"),
            "macd_signal": latest_value(data, "macd_signal"),
            "macd_hist": latest_value(data, "macd_hist"),
            "k": latest_value(data, "k"),
            "d": latest_value(data, "d"),
            "rsv": latest_value(data, "rsv"),
            "high_20": high_20,
            "high_60": high_60,
            "distance_from_20d_high": pct_change_from(close, high_20),
            "distance_from_60d_high": pct_change_from(close, high_60),
            "atr14": atr14,
            "atr_pct": safe_ratio(atr14, close),
            "volatility_20": latest_value(data, "volatility_20"),
            "macd_turn_positive": bool(
                len(data) >= 2
                and pd.notna(data["macd_hist"].iloc[-1])
                and pd.notna(data["macd_hist"].iloc[-2])
                and data["macd_hist"].iloc[-1] > 0
                and data["macd_hist"].iloc[-2] <= 0
            ),
            "breakout_20": bool(pd.notna(high_20) and close > high_20),
            "breakout_60": bool(pd.notna(high_60) and close > high_60),
        }
        row["price_above_ma5"] = bool(pd.notna(row["ma5"]) and close > row["ma5"])
        row["price_above_ma20"] = bool(pd.notna(row["ma20"]) and close > row["ma20"])
        row["price_above_ma60"] = bool(pd.notna(row["ma60"]) and close > row["ma60"])
        row["bullish_ma_order"] = bool(
            pd.notna(row["ma5"]) and pd.notna(row["ma20"]) and pd.notna(row["ma60"]) and row["ma5"] > row["ma20"] > row["ma60"]
        )
        row["bearish_ma_order"] = bool(
            pd.notna(row["ma5"]) and pd.notna(row["ma20"]) and pd.notna(row["ma60"]) and row["ma5"] < row["ma20"] < row["ma60"]
        )
        row["k_above_d"] = bool(pd.notna(row["k"]) and pd.notna(row["d"]) and row["k"] > row["d"])
        rows.append(row)

    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows)
    for definition in FILTER_DEFINITIONS:
        key = definition["key"]
        if key in result.columns:
            result[key] = pd.to_numeric(result[key], errors="coerce")
    for definition in BOOLEAN_FILTER_DEFINITIONS:
        key = definition["key"]
        if key in result.columns:
            result[key] = result[key].fillna(False).astype(bool)
    return result


def filter_definition_map() -> dict[str, dict]:
    return {definition["key"]: definition for definition in FILTER_DEFINITIONS}


def boolean_definition_map() -> dict[str, dict]:
    return {definition["key"]: definition for definition in BOOLEAN_FILTER_DEFINITIONS}


def numeric_display_bounds(df: pd.DataFrame, definition: dict) -> tuple[float, float] | None:
    key = definition["key"]
    if key not in df.columns:
        return None
    values = pd.to_numeric(df[key], errors="coerce").dropna()
    if values.empty:
        return None
    if definition.get("unit") == "pct":
        values = values * 100
    return float(values.min()), float(values.max())


def numeric_raw_to_display(value: float | None, definition: dict) -> float | None:
    if value is None:
        return None
    if definition.get("unit") == "pct":
        return float(value) * 100
    return float(value)


def numeric_display_to_raw(value: float | None, definition: dict) -> float | None:
    if value is None:
        return None
    if definition.get("unit") == "pct":
        return float(value) / 100
    return float(value)


def saved_query_strategies_path() -> Path:
    return Path("output") / "query_strategies.json"


def load_saved_query_strategies() -> list[dict]:
    path = saved_query_strategies_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict) and item.get("name")]


def save_query_strategy(strategy: dict) -> Path:
    path = saved_query_strategies_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    strategies = [item for item in load_saved_query_strategies() if item.get("name") != strategy.get("name")]
    strategies.append(strategy)
    path.write_text(json.dumps(strategies, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def set_query_controls_to_full_range(query_df: pd.DataFrame) -> None:
    st.session_state["filter_keyword"] = ""
    st.session_state["filter_market"] = []
    st.session_state["filter_industry"] = []
    for definition in FILTER_DEFINITIONS:
        bounds = numeric_display_bounds(query_df, definition)
        if bounds is None:
            continue
        key = definition["key"]
        st.session_state[f"filter_{key}_min"] = bounds[0]
        st.session_state[f"filter_{key}_max"] = bounds[1]
    for definition in BOOLEAN_FILTER_DEFINITIONS:
        st.session_state[f"filter_{definition['key']}"] = "全部"


def apply_strategy_example_to_query_controls(example: dict, query_df: pd.DataFrame) -> None:
    set_query_controls_to_full_range(query_df)
    st.session_state["filter_keyword"] = str(example.get("keyword", "") or "")
    st.session_state["filter_market"] = list(example.get("markets", []) or [])
    st.session_state["filter_industry"] = list(example.get("industries", []) or [])
    numeric_definitions = filter_definition_map()
    for key, limits in example.get("numeric", {}).items():
        definition = numeric_definitions.get(key)
        bounds = numeric_display_bounds(query_df, definition) if definition else None
        if definition is None or bounds is None:
            continue
        lower, upper = limits
        selected_min = numeric_raw_to_display(lower, definition)
        selected_max = numeric_raw_to_display(upper, definition)
        if selected_min is None:
            selected_min = bounds[0]
        if selected_max is None:
            selected_max = bounds[1]
        st.session_state[f"filter_{key}_min"] = max(bounds[0], min(bounds[1], selected_min))
        st.session_state[f"filter_{key}_max"] = max(bounds[0], min(bounds[1], selected_max))

    for key, expected in example.get("boolean", {}).items():
        st.session_state[f"filter_{key}"] = "是" if expected else "否"

    st.session_state["parameter_query_active_example"] = example["name"]
    st.session_state.pop("parameter_query_result", None)
    st.session_state.pop("parameter_query_context", None)


def format_strategy_example_conditions(example: dict) -> str:
    numeric_definitions = filter_definition_map()
    boolean_definitions = boolean_definition_map()
    parts = []
    if example.get("keyword"):
        parts.append(f"關鍵字={example['keyword']}")
    if example.get("markets"):
        parts.append("市場=" + ",".join(map(str, example["markets"])))
    if example.get("industries"):
        parts.append("產業=" + ",".join(map(str, example["industries"])))
    for key, expected in example.get("boolean", {}).items():
        label = boolean_definitions.get(key, {}).get("label", key)
        parts.append(f"{label}={'是' if expected else '否'}")
    for key, limits in example.get("numeric", {}).items():
        definition = numeric_definitions.get(key, {})
        label = definition.get("label", key)
        unit = "%" if definition.get("unit") == "pct" else ""
        lower, upper = limits
        lower_display = numeric_raw_to_display(lower, definition) if definition else lower
        upper_display = numeric_raw_to_display(upper, definition) if definition else upper
        if lower is None:
            parts.append(f"{label}<={upper_display:g}{unit}")
        elif upper is None:
            parts.append(f"{label}>={lower_display:g}{unit}")
        else:
            parts.append(f"{lower_display:g}{unit}<={label}<={upper_display:g}{unit}")
    return " / ".join(parts)


def collect_query_controls_as_strategy(name: str, description: str, query_df: pd.DataFrame) -> dict:
    numeric = {}
    for definition in FILTER_DEFINITIONS:
        key = definition["key"]
        bounds = numeric_display_bounds(query_df, definition)
        if bounds is None:
            continue
        selected_min = float(st.session_state.get(f"filter_{key}_min", bounds[0]))
        selected_max = float(st.session_state.get(f"filter_{key}_max", bounds[1]))
        lower = None if abs(selected_min - bounds[0]) < 1e-9 else numeric_display_to_raw(selected_min, definition)
        upper = None if abs(selected_max - bounds[1]) < 1e-9 else numeric_display_to_raw(selected_max, definition)
        if lower is not None or upper is not None:
            numeric[key] = (lower, upper)

    boolean = {}
    for definition in BOOLEAN_FILTER_DEFINITIONS:
        key = definition["key"]
        choice = st.session_state.get(f"filter_{key}", "全部")
        if choice != "全部":
            boolean[key] = choice == "是"

    return {
        "name": name,
        "source_strategy": f"custom_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "description": description or "自訂查詢策略。",
        "custom": True,
        "keyword": st.session_state.get("filter_keyword", ""),
        "markets": list(st.session_state.get("filter_market", []) or []),
        "industries": list(st.session_state.get("filter_industry", []) or []),
        "boolean": boolean,
        "numeric": numeric,
    }


def render_strategy_examples(query_df: pd.DataFrame) -> None:
    st.markdown("**策略範例**")
    st.caption("這裡先把原本五種策略改寫成可直接帶入本分頁的查詢參數。按下帶入後，請再按「查詢」更新結果。")
    examples = QUERY_STRATEGY_EXAMPLES + load_saved_query_strategies()
    columns = st.columns(min(5, max(1, len(examples))))
    for index, example in enumerate(examples):
        with columns[index % len(columns)]:
            with st.container(border=True):
                st.markdown(f"**{example['name']}**")
                if example.get("custom"):
                    st.caption("自訂策略")
                st.caption(example["description"])
                st.caption(format_strategy_example_conditions(example))
                button_key = f"apply_example_{example.get('source_strategy', example['name'])}_{index}"
                if st.button("帶入參數", key=button_key):
                    apply_strategy_example_to_query_controls(example, query_df)
                    st.rerun()
    active_example = st.session_state.get("parameter_query_active_example")
    if active_example:
        st.info(f"已帶入策略範例：{active_example}。確認條件後按「查詢」更新結果。")


def slider_step(minimum: float, maximum: float, unit: str | None) -> float:
    span = abs(maximum - minimum)
    if unit == "pct":
        return 0.1 if span <= 20 else 1.0
    if span <= 1:
        return 0.01
    if span <= 20:
        return 0.1
    if span <= 200:
        return 1.0
    return max(round(span / 100, 2), 1.0)


def apply_numeric_filter(df: pd.DataFrame, mask: pd.Series, definition: dict) -> pd.Series:
    key = definition["key"]
    if key not in df.columns:
        return mask
    values = pd.to_numeric(df[key], errors="coerce")
    available = values.dropna()
    if available.empty:
        return mask

    unit = definition.get("unit")
    display_values = available * 100 if unit == "pct" else available
    minimum = float(display_values.min())
    maximum = float(display_values.max())
    label = definition["label"] + (" (%)" if unit == "pct" else "")
    if minimum == maximum:
        st.caption(f"{label}: {minimum:,.2f}")
        return mask

    step = slider_step(minimum, maximum, unit)
    input_col1, input_col2 = st.columns(2)
    selected_min = input_col1.number_input(
        f"{label} 下限",
        value=minimum,
        step=step,
        format="%.4f",
        help=definition.get("help"),
        key=f"filter_{key}_min",
    )
    selected_max = input_col2.number_input(
        f"{label} 上限",
        value=maximum,
        step=step,
        format="%.4f",
        help=definition.get("help"),
        key=f"filter_{key}_max",
    )
    if selected_min > selected_max:
        selected_min, selected_max = selected_max, selected_min
    lower = selected_min / 100 if unit == "pct" else selected_min
    upper = selected_max / 100 if unit == "pct" else selected_max
    return mask & values.between(lower, upper)


def apply_boolean_filter(df: pd.DataFrame, mask: pd.Series, definition: dict) -> pd.Series:
    key = definition["key"]
    if key not in df.columns:
        return mask
    choice = st.selectbox(
        definition["label"],
        ["全部", "是", "否"],
        help=definition.get("help"),
        key=f"filter_{key}",
    )
    if choice == "全部":
        return mask
    expected = choice == "是"
    return mask & (df[key].fillna(False).astype(bool) == expected)


def render_parameter_query_tab_v2(
    price_data: dict[str, pd.DataFrame],
    stock_pool: list[dict],
    strategy_name: str,
    params: dict,
    holding_days: int,
    selected_start_date: date,
    selected_end_date: date,
) -> None:
    st.subheader("全部參數查詢")
    query_df = build_query_universe(price_data, stock_pool, strategy_name, params)
    if query_df.empty:
        st.info("目前分析區間內沒有可查詢的日K資料。")
        return

    strategy_display = get_strategy_display_name(strategy_name)
    summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)
    summary_col1.metric("目前策略", strategy_display)
    summary_col2.metric("回測天數", holding_days)
    summary_col3.metric("分析區間", f"{selected_start_date.isoformat()} ~ {selected_end_date.isoformat()}")
    summary_col4.metric("可查詢股票", len(query_df))
    if params:
        st.caption("目前策略參數：" + " / ".join(f"{key}={value}" for key, value in params.items()))
    st.caption("ROE稅後、EPS、營收、法人與融資融券等不是日K可推導欄位；需要新增基本面或籌碼資料表後才能加入這裡。")

    render_strategy_examples(query_df)
    save_message = st.session_state.pop("query_strategy_save_message", None)
    if save_message:
        st.success(save_message)

    clear_col1, clear_col2 = st.columns([1, 4])
    if clear_col1.button("清空參數", type="secondary"):
        set_query_controls_to_full_range(query_df)
        st.session_state.pop("parameter_query_active_example", None)
        st.session_state.pop("parameter_query_result", None)
        st.session_state.pop("parameter_query_context", None)
        st.rerun()
    clear_col2.caption("清空後會把關鍵字、市場、產業、布林條件與所有 range 都恢復成「全部」。")

    market_options = sorted(value for value in query_df.get("market", pd.Series(dtype=str)).dropna().astype(str).unique() if value)
    industry_options = sorted(
        value for value in query_df.get("industry_category", pd.Series(dtype=str)).dropna().astype(str).unique() if value
    )
    if "filter_market" in st.session_state:
        st.session_state["filter_market"] = [value for value in st.session_state["filter_market"] if value in market_options]
    if "filter_industry" in st.session_state:
        st.session_state["filter_industry"] = [value for value in st.session_state["filter_industry"] if value in industry_options]

    query_context = json.dumps(
        {
            "strategy_name": strategy_name,
            "params": params,
            "holding_days": holding_days,
            "start": selected_start_date.isoformat(),
            "end": selected_end_date.isoformat(),
            "rows": len(query_df),
            "latest": str(query_df["latest_date"].max()) if "latest_date" in query_df.columns else "",
        },
        sort_keys=True,
        default=str,
    )

    with st.form("parameter_query_form"):
        mask = pd.Series(True, index=query_df.index)
        action_col1, action_col2 = st.columns([1, 4])
        submitted = action_col1.form_submit_button("查詢", type="primary")
        action_col2.caption("查詢鍵已放在最上方；調整條件後，按查詢才會更新下方結果。")
        top_col1, top_col2, top_col3 = st.columns([2, 1, 1])
        keyword = top_col1.text_input(
            "股票代號 / 名稱 / 主題關鍵字",
            help="可輸入股票代號、股票名稱或主題標籤的一部分來篩選。",
            key="filter_keyword",
        ).strip()
        if keyword:
            keyword_mask = (
                query_df["stock_id"].astype(str).str.contains(keyword, case=False, na=False)
                | query_df["stock_name"].astype(str).str.contains(keyword, case=False, na=False)
                | query_df.get("theme_tags", pd.Series("", index=query_df.index)).astype(str).str.contains(keyword, case=False, na=False)
            )
            mask &= keyword_mask

        selected_markets = top_col2.multiselect("市場別", market_options, help="依上市、上櫃等市場分類篩選。", key="filter_market")
        if selected_markets:
            mask &= query_df["market"].astype(str).isin(selected_markets)

        selected_industries = top_col3.multiselect(
            "產業類別",
            industry_options,
            help="依股票池中的產業分類篩選。",
            key="filter_industry",
        )
        if selected_industries:
            mask &= query_df["industry_category"].astype(str).isin(selected_industries)

        st.markdown("**布林條件**")
        bool_cols = st.columns(4)
        for index, definition in enumerate(BOOLEAN_FILTER_DEFINITIONS):
            with bool_cols[index % len(bool_cols)]:
                mask = apply_boolean_filter(query_df, mask, definition)

        definitions_by_category = {
            category: [definition for definition in FILTER_DEFINITIONS if definition["category"] == category]
            for category in FILTER_CATEGORY_ORDER
        }
        for category in FILTER_CATEGORY_ORDER:
            definitions = definitions_by_category.get(category, [])
            available_definitions = [definition for definition in definitions if definition["key"] in query_df.columns]
            if not available_definitions:
                continue
            st.markdown(f"**{category}**")
            columns = st.columns(3)
            for index, definition in enumerate(available_definitions):
                with columns[index % len(columns)]:
                    mask = apply_numeric_filter(query_df, mask, definition)

        with st.expander("儲存新策略", expanded=False):
            save_strategy_name = st.text_input(
                "策略名稱",
                help="輸入名稱後，可把目前表單裡的條件儲存成自訂策略範例。",
                key="save_strategy_name",
            )
            save_strategy_description = st.text_area(
                "策略說明",
                help="簡短描述這組條件想找的股票型態。",
                key="save_strategy_description",
            )

        submit_col1, submit_col2, submit_col3 = st.columns([1, 1, 3])
        submitted = submit_col1.form_submit_button("查詢", type="primary")
        save_submitted = submit_col2.form_submit_button("儲存新策略")
        submit_col3.caption("調整上方條件不會重新查詢；按下查詢後才會更新下方結果。儲存新策略會保存目前表單條件。")

    if save_submitted_top or save_submitted:
        strategy_name_to_save = save_strategy_name_top.strip() if save_submitted_top else save_strategy_name.strip()
        strategy_description_to_save = (
            save_strategy_description_top.strip()
            if save_submitted_top
            else save_strategy_description.strip()
        )
        if not strategy_name_to_save:
            st.warning("請先輸入策略名稱。")
        else:
            saved_strategy = collect_query_controls_as_strategy(
                strategy_name_to_save,
                strategy_description_to_save,
                query_df,
            )
            save_path = save_query_strategy(saved_strategy)
            st.session_state["query_strategy_save_message"] = f"已儲存策略：{strategy_name_to_save}（{save_path}）"
            st.session_state["parameter_query_active_example"] = strategy_name_to_save
            st.rerun()

    if submitted:
        filtered = query_df.loc[mask].sort_values(["current_strategy_signal", "volume_ratio_20"], ascending=[False, False])
        st.session_state["parameter_query_result"] = filtered
        st.session_state["parameter_query_context"] = query_context
    elif st.session_state.get("parameter_query_context") == query_context and "parameter_query_result" in st.session_state:
        filtered = st.session_state["parameter_query_result"]
    else:
        st.info("設定查詢條件後，請按「查詢」產生結果。")
        return

    st.caption(f"符合條件：{len(filtered)} / {len(query_df)} 檔")
    result_columns = [column for column in FILTER_RESULT_LABELS if column in filtered.columns]
    display_df = filtered[result_columns].copy()
    percent_columns = ["day_return", "bias20", "atr_pct", "volatility_20", "return_20d"]
    for column in percent_columns:
        if column in display_df.columns:
            display_df[column] = display_df[column] * 100
    st.dataframe(localize_columns(display_df, FILTER_RESULT_LABELS), width="stretch", height=420)

    with st.expander("全部欄位資料", expanded=False):
        full_display = filtered.copy()
        pct_columns = [definition["key"] for definition in FILTER_DEFINITIONS if definition.get("unit") == "pct"]
        for column in pct_columns:
            if column in full_display.columns:
                full_display[column] = full_display[column] * 100
        st.dataframe(full_display, width="stretch", height=520)

    csv_data = filtered.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        "下載目前查詢結果 CSV",
        csv_data,
        file_name="parameter_query_result.csv",
        mime="text/csv",
    )


def render_parameter_query_tab_v3(
    price_data: dict[str, pd.DataFrame],
    stock_pool: list[dict],
    strategy_name: str,
    params: dict,
    holding_days: int,
    selected_start_date: date,
    selected_end_date: date,
) -> None:
    st.subheader("全部參數查詢")
    query_df = build_query_universe(price_data, stock_pool, strategy_name, params)
    if query_df.empty:
        st.info("目前分析區間內沒有可查詢的日K資料。")
        return

    strategy_display = get_strategy_display_name(strategy_name)
    summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)
    summary_col1.metric("目前策略", strategy_display)
    summary_col2.metric("回測天數", holding_days)
    summary_col3.metric("分析區間", f"{selected_start_date.isoformat()} ~ {selected_end_date.isoformat()}")
    summary_col4.metric("可查詢股票", len(query_df))
    if params:
        st.caption("目前策略參數：" + " / ".join(f"{key}={value}" for key, value in params.items()))
    st.caption("ROE稅後、EPS、營收、法人與融資融券等不是日K可推導欄位；需要新增基本面或籌碼資料表後才能加入這裡。")

    render_strategy_examples(query_df)
    save_message = st.session_state.pop("query_strategy_save_message", None)
    if save_message:
        st.success(save_message)

    market_options = sorted(value for value in query_df.get("market", pd.Series(dtype=str)).dropna().astype(str).unique() if value)
    industry_options = sorted(
        value for value in query_df.get("industry_category", pd.Series(dtype=str)).dropna().astype(str).unique() if value
    )
    if "filter_market" in st.session_state:
        st.session_state["filter_market"] = [value for value in st.session_state["filter_market"] if value in market_options]
    if "filter_industry" in st.session_state:
        st.session_state["filter_industry"] = [value for value in st.session_state["filter_industry"] if value in industry_options]

    clear_col1, clear_col2 = st.columns([1, 4])
    if clear_col1.button("清空參數", type="secondary"):
        set_query_controls_to_full_range(query_df)
        st.session_state.pop("parameter_query_active_example", None)
        st.session_state.pop("parameter_query_result", None)
        st.session_state.pop("parameter_query_context", None)
        st.rerun()
    clear_col2.caption("清空會把關鍵字、市場、產業、布林條件與所有 range 都恢復成「全部」。")

    query_context = json.dumps(
        {
            "strategy_name": strategy_name,
            "params": params,
            "holding_days": holding_days,
            "start": selected_start_date.isoformat(),
            "end": selected_end_date.isoformat(),
            "rows": len(query_df),
            "latest": str(query_df["latest_date"].max()) if "latest_date" in query_df.columns else "",
        },
        sort_keys=True,
        default=str,
    )

    with st.form("parameter_query_form"):
        mask = pd.Series(True, index=query_df.index)
        action_col1, action_col2 = st.columns([1, 4])
        submitted = action_col1.form_submit_button("查詢", type="primary")
        action_col2.caption("查詢鍵在最上方；調整條件後，按查詢才會更新下方結果。")

        save_top_col1, save_top_col2, save_top_col3 = st.columns([2, 3, 1])
        save_strategy_name_top = save_top_col1.text_input(
            "策略名稱",
            help="輸入名稱後，可把目前表單裡的條件儲存成自訂策略範例。",
            key="save_strategy_name_top",
        )
        save_strategy_description_top = save_top_col2.text_input(
            "策略說明",
            help="簡短描述這組條件想找的股票型態。",
            key="save_strategy_description_top",
        )
        save_submitted_top = save_top_col3.form_submit_button("儲存新策略")

        top_col1, top_col2, top_col3 = st.columns([2, 1, 1])
        keyword = top_col1.text_input(
            "股票代號 / 名稱 / 主題關鍵字",
            help="可輸入股票代號、股票名稱或主題標籤的一部分來篩選。",
            key="filter_keyword",
        ).strip()
        if keyword:
            keyword_mask = (
                query_df["stock_id"].astype(str).str.contains(keyword, case=False, na=False)
                | query_df["stock_name"].astype(str).str.contains(keyword, case=False, na=False)
                | query_df.get("theme_tags", pd.Series("", index=query_df.index)).astype(str).str.contains(keyword, case=False, na=False)
            )
            mask &= keyword_mask

        selected_markets = top_col2.multiselect("市場別", market_options, help="依上市、上櫃等市場分類篩選。", key="filter_market")
        if selected_markets:
            mask &= query_df["market"].astype(str).isin(selected_markets)

        selected_industries = top_col3.multiselect(
            "產業類別",
            industry_options,
            help="依股票池中的產業分類篩選。",
            key="filter_industry",
        )
        if selected_industries:
            mask &= query_df["industry_category"].astype(str).isin(selected_industries)

        st.markdown("**布林條件**")
        bool_cols = st.columns(4)
        for index, definition in enumerate(BOOLEAN_FILTER_DEFINITIONS):
            with bool_cols[index % len(bool_cols)]:
                mask = apply_boolean_filter(query_df, mask, definition)

        definitions_by_category = {
            category: [definition for definition in FILTER_DEFINITIONS if definition["category"] == category]
            for category in FILTER_CATEGORY_ORDER
        }
        for category in FILTER_CATEGORY_ORDER:
            definitions = definitions_by_category.get(category, [])
            available_definitions = [definition for definition in definitions if definition["key"] in query_df.columns]
            if not available_definitions:
                continue
            st.markdown(f"**{category}**")
            columns = st.columns(3)
            for index, definition in enumerate(available_definitions):
                with columns[index % len(columns)]:
                    mask = apply_numeric_filter(query_df, mask, definition)

        save_submitted = False

    if save_submitted_top or save_submitted:
        strategy_name_to_save = save_strategy_name_top.strip()
        strategy_description_to_save = save_strategy_description_top.strip()
        if not strategy_name_to_save:
            st.warning("請先輸入策略名稱。")
        else:
            saved_strategy = collect_query_controls_as_strategy(
                strategy_name_to_save,
                strategy_description_to_save,
                query_df,
            )
            save_path = save_query_strategy(saved_strategy)
            st.session_state["query_strategy_save_message"] = f"已儲存策略：{strategy_name_to_save}（{save_path}）"
            st.session_state["parameter_query_active_example"] = strategy_name_to_save
            st.rerun()

    if submitted:
        filtered = query_df.loc[mask].sort_values(["current_strategy_signal", "volume_ratio_20"], ascending=[False, False])
        st.session_state["parameter_query_result"] = filtered
        st.session_state["parameter_query_context"] = query_context
    elif st.session_state.get("parameter_query_context") == query_context and "parameter_query_result" in st.session_state:
        filtered = st.session_state["parameter_query_result"]
    else:
        st.info("設定查詢條件後，請按「查詢」產生結果。")
        return

    st.caption(f"符合條件：{len(filtered)} / {len(query_df)} 檔")
    result_columns = [column for column in FILTER_RESULT_LABELS if column in filtered.columns]
    display_df = filtered[result_columns].copy()
    percent_columns = ["day_return", "bias20", "atr_pct", "volatility_20", "return_20d"]
    for column in percent_columns:
        if column in display_df.columns:
            display_df[column] = display_df[column] * 100
    st.dataframe(localize_columns(display_df, FILTER_RESULT_LABELS), width="stretch", height=420)

    with st.expander("全部欄位資料", expanded=False):
        full_display = filtered.copy()
        pct_columns = [definition["key"] for definition in FILTER_DEFINITIONS if definition.get("unit") == "pct"]
        for column in pct_columns:
            if column in full_display.columns:
                full_display[column] = full_display[column] * 100
        st.dataframe(full_display, width="stretch", height=520)

    csv_data = filtered.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        "下載目前查詢結果 CSV",
        csv_data,
        file_name="parameter_query_result.csv",
        mime="text/csv",
    )


def render_parameter_query_tab_v4(
    price_data: dict[str, pd.DataFrame],
    stock_pool: list[dict],
    strategy_name: str,
    params: dict,
    holding_days: int,
    selected_start_date: date,
    selected_end_date: date,
) -> None:
    st.subheader("全部參數查詢")
    query_df = build_query_universe(price_data, stock_pool, strategy_name, params)
    if query_df.empty:
        st.info("目前分析區間內沒有可查詢的日K資料。")
        return

    strategy_display = get_strategy_display_name(strategy_name)
    summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)
    summary_col1.metric("目前策略", strategy_display)
    summary_col2.metric("回測天數", holding_days)
    summary_col3.metric("分析區間", f"{selected_start_date.isoformat()} ~ {selected_end_date.isoformat()}")
    summary_col4.metric("可查詢股票", len(query_df))
    if params:
        st.caption("目前策略參數：" + " / ".join(f"{key}={value}" for key, value in params.items()))
    st.caption("ROE稅後、EPS、營收、法人與融資融券等不是日K可推導欄位；需要新增基本面或籌碼資料表後才能加入這裡。")

    render_strategy_examples(query_df)
    save_message = st.session_state.pop("query_strategy_save_message", None)
    if save_message:
        st.success(save_message)

    market_options = sorted(value for value in query_df.get("market", pd.Series(dtype=str)).dropna().astype(str).unique() if value)
    industry_options = sorted(
        value for value in query_df.get("industry_category", pd.Series(dtype=str)).dropna().astype(str).unique() if value
    )
    if "filter_market" in st.session_state:
        st.session_state["filter_market"] = [value for value in st.session_state["filter_market"] if value in market_options]
    if "filter_industry" in st.session_state:
        st.session_state["filter_industry"] = [value for value in st.session_state["filter_industry"] if value in industry_options]

    clear_col1, clear_col2 = st.columns([1, 4])
    if clear_col1.button("清空參數", type="secondary"):
        set_query_controls_to_full_range(query_df)
        st.session_state.pop("parameter_query_active_example", None)
        st.session_state.pop("parameter_query_result", None)
        st.session_state.pop("parameter_query_context", None)
        st.rerun()
    clear_col2.caption("清空會把關鍵字、市場、產業、布林條件與所有 range 都恢復成「全部」。")

    query_context = json.dumps(
        {
            "strategy_name": strategy_name,
            "params": params,
            "holding_days": holding_days,
            "start": selected_start_date.isoformat(),
            "end": selected_end_date.isoformat(),
            "rows": len(query_df),
            "latest": str(query_df["latest_date"].max()) if "latest_date" in query_df.columns else "",
        },
        sort_keys=True,
        default=str,
    )

    with st.form("parameter_query_form"):
        mask = pd.Series(True, index=query_df.index)
        action_col1, action_col2, action_col3 = st.columns([1, 2, 2])
        submitted = action_col1.form_submit_button("查詢", type="primary")
        save_submitted = action_col2.form_submit_button("儲存新策略")
        action_col3.caption("上方按鈕固定在最前面；調整條件後，按查詢才更新結果。")

        save_top_col1, save_top_col2 = st.columns([2, 3])
        save_strategy_name_top = save_top_col1.text_input(
            "策略名稱",
            help="輸入名稱後，可把目前表單裡的條件儲存成自訂策略範例。",
            key="save_strategy_name_top",
        )
        save_strategy_description_top = save_top_col2.text_input(
            "策略說明",
            help="簡短描述這組條件想找的股票型態。",
            key="save_strategy_description_top",
        )

        top_col1, top_col2, top_col3 = st.columns([2, 1, 1])
        keyword = top_col1.text_input(
            "股票代號 / 名稱 / 主題關鍵字",
            help="可輸入股票代號、股票名稱或主題標籤的一部分來篩選。",
            key="filter_keyword",
        ).strip()
        if keyword:
            keyword_mask = (
                query_df["stock_id"].astype(str).str.contains(keyword, case=False, na=False)
                | query_df["stock_name"].astype(str).str.contains(keyword, case=False, na=False)
                | query_df.get("theme_tags", pd.Series("", index=query_df.index)).astype(str).str.contains(keyword, case=False, na=False)
            )
            mask &= keyword_mask

        selected_markets = top_col2.multiselect("市場別", market_options, help="依上市、上櫃等市場分類篩選。", key="filter_market")
        if selected_markets:
            mask &= query_df["market"].astype(str).isin(selected_markets)

        selected_industries = top_col3.multiselect(
            "產業類別",
            industry_options,
            help="依股票池中的產業分類篩選。",
            key="filter_industry",
        )
        if selected_industries:
            mask &= query_df["industry_category"].astype(str).isin(selected_industries)

        with st.expander("布林條件", expanded=False):
            bool_cols = st.columns(4)
            for index, definition in enumerate(BOOLEAN_FILTER_DEFINITIONS):
                with bool_cols[index % len(bool_cols)]:
                    mask = apply_boolean_filter(query_df, mask, definition)

        definitions_by_category = {
            category: [definition for definition in FILTER_DEFINITIONS if definition["category"] == category]
            for category in FILTER_CATEGORY_ORDER
        }
        for category in FILTER_CATEGORY_ORDER:
            definitions = definitions_by_category.get(category, [])
            available_definitions = [definition for definition in definitions if definition["key"] in query_df.columns]
            if not available_definitions:
                continue
            with st.expander(str(category), expanded=False):
                columns = st.columns(3)
                for index, definition in enumerate(available_definitions):
                    with columns[index % len(columns)]:
                        mask = apply_numeric_filter(query_df, mask, definition)

    if save_submitted:
        strategy_name_to_save = save_strategy_name_top.strip()
        strategy_description_to_save = save_strategy_description_top.strip()
        if not strategy_name_to_save:
            st.warning("請先輸入策略名稱。")
        else:
            saved_strategy = collect_query_controls_as_strategy(
                strategy_name_to_save,
                strategy_description_to_save,
                query_df,
            )
            save_path = save_query_strategy(saved_strategy)
            st.session_state["query_strategy_save_message"] = f"已儲存策略：{strategy_name_to_save}（{save_path}）"
            st.session_state["parameter_query_active_example"] = strategy_name_to_save
            st.rerun()

    if submitted:
        filtered = query_df.loc[mask].sort_values(["current_strategy_signal", "volume_ratio_20"], ascending=[False, False])
        st.session_state["parameter_query_result"] = filtered
        st.session_state["parameter_query_context"] = query_context
    elif st.session_state.get("parameter_query_context") == query_context and "parameter_query_result" in st.session_state:
        filtered = st.session_state["parameter_query_result"]
    else:
        st.info("設定查詢條件後，請按「查詢」產生結果。")
        return

    st.caption(f"符合條件：{len(filtered)} / {len(query_df)} 檔")
    result_columns = [column for column in FILTER_RESULT_LABELS if column in filtered.columns]
    display_df = filtered[result_columns].copy()
    percent_columns = ["day_return", "bias20", "atr_pct", "volatility_20", "return_20d"]
    for column in percent_columns:
        if column in display_df.columns:
            display_df[column] = display_df[column] * 100
    st.dataframe(localize_columns(display_df, FILTER_RESULT_LABELS), width="stretch", height=420)

    with st.expander("全部欄位資料", expanded=False):
        full_display = filtered.copy()
        pct_columns = [definition["key"] for definition in FILTER_DEFINITIONS if definition.get("unit") == "pct"]
        for column in pct_columns:
            if column in full_display.columns:
                full_display[column] = full_display[column] * 100
        st.dataframe(full_display, width="stretch", height=520)

    csv_data = filtered.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        "下載目前查詢結果 CSV",
        csv_data,
        file_name="parameter_query_result.csv",
        mime="text/csv",
    )


def render_parameter_query_tab(
    price_data: dict[str, pd.DataFrame],
    stock_pool: list[dict],
    strategy_name: str,
    params: dict,
    holding_days: int,
    selected_start_date: date,
    selected_end_date: date,
) -> None:
    render_parameter_query_tab_v4(
        price_data,
        stock_pool,
        strategy_name,
        params,
        holding_days,
        selected_start_date,
        selected_end_date,
    )
    return

    st.subheader("全部參數查詢")
    query_df = build_query_universe(price_data, stock_pool, strategy_name, params)
    if query_df.empty:
        st.info("目前分析區間內沒有可查詢的日K資料。")
        return

    strategy_display = get_strategy_display_name(strategy_name)
    summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)
    summary_col1.metric("目前策略", strategy_display)
    summary_col2.metric("回測天數", holding_days)
    summary_col3.metric("分析區間", f"{selected_start_date.isoformat()} ~ {selected_end_date.isoformat()}")
    summary_col4.metric("可查詢股票", len(query_df))
    if params:
        st.caption("目前策略參數：" + " / ".join(f"{key}={value}" for key, value in params.items()))
    st.caption("ROE稅後、EPS、營收、法人與融資融券等不是日K可推導欄位；需要新增基本面或籌碼資料表後才能加入這裡。")

    mask = pd.Series(True, index=query_df.index)
    top_col1, top_col2, top_col3 = st.columns([2, 1, 1])
    keyword = top_col1.text_input(
        "股票代號 / 名稱 / 主題關鍵字",
        help="可輸入股票代號、股票名稱或主題標籤的一部分來篩選。",
    ).strip()
    if keyword:
        keyword_mask = (
            query_df["stock_id"].astype(str).str.contains(keyword, case=False, na=False)
            | query_df["stock_name"].astype(str).str.contains(keyword, case=False, na=False)
            | query_df.get("theme_tags", pd.Series("", index=query_df.index)).astype(str).str.contains(keyword, case=False, na=False)
        )
        mask &= keyword_mask

    market_options = sorted(value for value in query_df.get("market", pd.Series(dtype=str)).dropna().astype(str).unique() if value)
    selected_markets = top_col2.multiselect("市場別", market_options, help="依上市、上櫃等市場分類篩選。")
    if selected_markets:
        mask &= query_df["market"].astype(str).isin(selected_markets)

    industry_options = sorted(
        value for value in query_df.get("industry_category", pd.Series(dtype=str)).dropna().astype(str).unique() if value
    )
    selected_industries = top_col3.multiselect("產業類別", industry_options, help="依股票池中的產業分類篩選。")
    if selected_industries:
        mask &= query_df["industry_category"].astype(str).isin(selected_industries)

    st.markdown("**布林條件**")
    bool_cols = st.columns(4)
    for index, definition in enumerate(BOOLEAN_FILTER_DEFINITIONS):
        with bool_cols[index % len(bool_cols)]:
            mask = apply_boolean_filter(query_df, mask, definition)

    definitions_by_category = {
        category: [definition for definition in FILTER_DEFINITIONS if definition["category"] == category]
        for category in FILTER_CATEGORY_ORDER
    }
    for category in FILTER_CATEGORY_ORDER:
        definitions = definitions_by_category.get(category, [])
        available_definitions = [definition for definition in definitions if definition["key"] in query_df.columns]
        if not available_definitions:
            continue
        st.markdown(f"**{category}**")
        columns = st.columns(3)
        for index, definition in enumerate(available_definitions):
            with columns[index % len(columns)]:
                mask = apply_numeric_filter(query_df, mask, definition)

    filtered = query_df.loc[mask].sort_values(["current_strategy_signal", "volume_ratio_20"], ascending=[False, False])
    st.caption(f"符合條件：{len(filtered)} / {len(query_df)} 檔")
    result_columns = [column for column in FILTER_RESULT_LABELS if column in filtered.columns]
    display_df = filtered[result_columns].copy()
    percent_columns = ["day_return", "bias20", "atr_pct", "volatility_20", "return_20d"]
    for column in percent_columns:
        if column in display_df.columns:
            display_df[column] = display_df[column] * 100
    st.dataframe(localize_columns(display_df, FILTER_RESULT_LABELS), width="stretch", height=420)

    with st.expander("全部欄位資料", expanded=False):
        full_display = filtered.copy()
        pct_columns = [definition["key"] for definition in FILTER_DEFINITIONS if definition.get("unit") == "pct"]
        for column in pct_columns:
            if column in full_display.columns:
                full_display[column] = full_display[column] * 100
        st.dataframe(full_display, width="stretch", height=520)

    csv_data = filtered.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        "下載目前查詢結果 CSV",
        csv_data,
        file_name="parameter_query_result.csv",
        mime="text/csv",
    )


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

    tab_query, tab_screen, tab_chart, tab_backtest, tab_report, tab_limits = st.tabs(
        ["參數查詢", "候選股", "圖表", "回測", "報告", "限制"]
    )

    with tab_query:
        render_parameter_query_tab(
            price_data,
            stock_pool,
            strategy_name,
            params,
            holding_days,
            selected_start_date,
            selected_end_date,
        )

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
        st.subheader("個股研報")
        st.caption(
            "三種具名格式：個股一頁紙研報（HTML）、同業比較表（Excel）、"
            "三情境交易計畫（HTML，可瀏覽器列印成 PDF）。"
        )

        if ranked.empty:
            st.info("沒有候選股可產生研報。請先在左側調整策略，產出 Top N 候選股。")
        else:
            candidate_records = ranked.to_dict("records")
            label_to_id = {
                f"{r['stock_id']} {r['stock_name']}": str(r["stock_id"])
                for r in candidate_records
            }

            col_a, col_b = st.columns([3, 2])
            with col_a:
                focus_label = st.selectbox("選擇焦點個股", list(label_to_id.keys()))
                focus_stock_id = label_to_id[focus_label]
            with col_b:
                audience_label_to_key = {
                    AUDIENCE_LABELS[AUDIENCE_SELF_TRADE]: AUDIENCE_SELF_TRADE,
                    AUDIENCE_LABELS[AUDIENCE_RETAIL]: AUDIENCE_RETAIL,
                    AUDIENCE_LABELS[AUDIENCE_PRO]: AUDIENCE_PRO,
                }
                audience_label = st.selectbox(
                    "一頁紙研報讀者模式",
                    list(audience_label_to_key.keys()),
                )
                audience_key = audience_label_to_key[audience_label]

            focus_meta = next(
                (s for s in stock_pool if str(s.get("stock_id")) == focus_stock_id),
                None,
            )
            focus_prices = price_data.get(focus_stock_id)

            if focus_meta is None or focus_prices is None or focus_prices.empty:
                st.warning("焦點個股缺少基本資料或股價資料，無法生成研報。")
            else:
                reports_dir = output_dir / "reports"
                if st.button("產生三份研報", type="primary"):
                    with st.spinner("正在生成 tear-sheet / comp-sheet / bull-bear..."):
                        try:
                            tear_path = generate_tear_sheet(
                                focus_stock_id,
                                focus_meta.get("stock_name", ""),
                                focus_meta.get("industry_category", ""),
                                focus_meta.get("market", ""),
                                focus_prices,
                                reports_dir / f"{focus_stock_id}_tear_sheet.html",
                                audience=audience_key,
                            )
                        except Exception as exc:
                            tear_path = None
                            st.error(f"Tear Sheet 生成失敗：{exc}")

                        try:
                            comp_path = generate_comp_sheet(
                                focus_stock_id,
                                stock_pool,
                                price_data,
                                reports_dir / f"{focus_stock_id}_comp_sheet.xlsx",
                            )
                        except Exception as exc:
                            comp_path = None
                            st.error(f"Comp Sheet 生成失敗：{exc}")

                        try:
                            bull_path = generate_bull_bear(
                                focus_stock_id,
                                focus_meta.get("stock_name", ""),
                                focus_meta.get("industry_category", ""),
                                focus_meta.get("market", ""),
                                focus_prices,
                                reports_dir / f"{focus_stock_id}_bull_bear.html",
                            )
                        except Exception as exc:
                            bull_path = None
                            st.error(f"Bull-Bear 生成失敗：{exc}")

                    st.success("研報已產出，請下載：")
                    for label, path in [
                        ("個股一頁紙研報（HTML）", tear_path),
                        ("同業比較表（Excel）", comp_path),
                        ("三情境交易計畫（HTML，可列印 PDF）", bull_path),
                    ]:
                        if not path:
                            continue
                        path_obj = Path(path)
                        if path_obj.exists():
                            with open(path_obj, "rb") as fh:
                                st.download_button(
                                    label,
                                    fh.read(),
                                    file_name=path_obj.name,
                                    mime="application/octet-stream",
                                    key=f"dl_{path_obj.name}",
                                )
                            st.caption(f"已存：{path_obj}")

            with st.expander("舊版 Markdown 報告（保留作對照）", expanded=False):
                if st.button("產生全部 Markdown 報告", key="legacy_md_btn"):
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
