"""Bull / Bear / Base 三情境交易計畫。

Modeled after Daloopa's `bull-bear` skill: turn current technical structure
into three concrete trade plans (bull / base / bear) with explicit entry,
stop, target and catalyst per scenario.

Output: HTML (single self-contained file). Browser-print → PDF.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from reports.base import (
    StockSnapshot,
    build_snapshot,
    fmt_num,
    fmt_pct,
    report_disclaimer,
    sparkline_svg,
    today_str,
    trend_label,
)


def generate_bull_bear(
    stock_id: str,
    stock_name: str,
    industry: str,
    market: str,
    prices: pd.DataFrame,
    output_path: str | Path,
) -> str:
    snap = build_snapshot(stock_id, stock_name, industry, market, prices)
    spark = prices.sort_values("date")["close"].tail(120).tolist()

    bull = _bull_scenario(snap)
    base = _base_scenario(snap)
    bear = _bear_scenario(snap)

    html = _render_html(snap, spark, bull, base, bear)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return str(path)


def _bull_scenario(snap: StockSnapshot) -> dict:
    """突破情境：站上 20D 高 + 多頭排列確認。"""
    entry = snap.high_20 if not pd.isna(snap.high_20) else snap.close
    stop = entry - 1.5 * snap.atr14 if not pd.isna(snap.atr14) else entry * 0.95
    target1 = entry + 2 * snap.atr14 if not pd.isna(snap.atr14) else entry * 1.07
    target2 = max(snap.high_52w, entry + 4 * snap.atr14) if not pd.isna(snap.atr14) else entry * 1.15
    rr = (target1 - entry) / (entry - stop) if (entry - stop) > 0 else 0
    return {
        "name": "樂觀情境（Bull）",
        "color": "#15803d",
        "thesis": "突破 20 日高點 + 多頭排列確立，動能加速。",
        "trigger": f"收盤站上 NT$ {fmt_num(snap.high_20)}（20 日高）且量能 > 20 日均量 1.2 倍。",
        "entry": entry,
        "stop": stop,
        "target1": target1,
        "target2": target2,
        "rr": rr,
        "horizon": "5–20 個交易日",
        "catalyst": "產業利多、財報優於預期、權值股拉抬、外資連續買超。",
        "invalidate": f"收盤跌破 NT$ {fmt_num(stop)} 或失守 MA20 NT$ {fmt_num(snap.ma20)}。",
        "size": "ATR×1 → 部位 = 風險預算 / (entry - stop)，單筆風險 ≤ 總資金 1%。",
    }


def _base_scenario(snap: StockSnapshot) -> dict:
    """區間情境：在 20D 區間內波段操作。"""
    entry = snap.ma20 if not pd.isna(snap.ma20) else snap.close
    stop = snap.low_20 if not pd.isna(snap.low_20) else entry * 0.94
    target = snap.high_20 if not pd.isna(snap.high_20) else entry * 1.06
    rr = (target - entry) / (entry - stop) if (entry - stop) > 0 else 0
    return {
        "name": "中性情境（Base）",
        "color": "#1f6feb",
        "thesis": "區間整理；於 MA20 附近承接，於 20 日高出場。",
        "trigger": f"回測 MA20 NT$ {fmt_num(snap.ma20)} 帶量止跌、RSI 回到 45–55。",
        "entry": entry,
        "stop": stop,
        "target1": target,
        "target2": None,
        "rr": rr,
        "horizon": "5–15 個交易日",
        "catalyst": "大盤橫盤、產業中性、缺乏明確催化劑。",
        "invalidate": f"跌破 20 日低 NT$ {fmt_num(snap.low_20)} → 轉為 Bear 處理。",
        "size": "部位 ≤ Bull 情境的 50%，因勝率與賠率較平庸。",
    }


def _bear_scenario(snap: StockSnapshot) -> dict:
    """悲觀情境：跌破支撐 → 觀望或反向。"""
    entry = snap.low_20 if not pd.isna(snap.low_20) else snap.close
    stop = snap.ma20 if not pd.isna(snap.ma20) else entry * 1.05
    target = entry - 2 * snap.atr14 if not pd.isna(snap.atr14) else entry * 0.92
    rr = (entry - target) / (stop - entry) if (stop - entry) > 0 else 0
    return {
        "name": "悲觀情境（Bear）",
        "color": "#b91c1c",
        "thesis": "跌破 20 日低，趨勢轉空，避免逆勢承接。",
        "trigger": f"收盤跌破 NT$ {fmt_num(snap.low_20)}（20 日低）且 MA20 反轉向下。",
        "entry": entry,
        "stop": stop,
        "target1": target,
        "target2": None,
        "rr": rr,
        "horizon": "5–10 個交易日（短）",
        "catalyst": "產業利空、大盤系統性風險、權值股下殺、外資連續賣超。",
        "invalidate": f"反彈站回 MA20 NT$ {fmt_num(snap.ma20)} 並守穩。",
        "size": "現股建議觀望；融券 / 反向 ETF 操作部位 ≤ 總資金 5%。",
    }


def _render_html(
    snap: StockSnapshot,
    spark: list[float],
    bull: dict,
    base: dict,
    bear: dict,
) -> str:
    spark_svg = sparkline_svg(spark, width=320, height=56)
    trend = trend_label(snap)

    cards_html = "".join(_scenario_card(s) for s in (bull, base, bear))

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<title>{snap.stock_id} {snap.stock_name} Bull / Bear / Base</title>
<style>
  @media print {{ body {{ margin: 12mm; }} .no-print {{ display:none; }} }}
  body {{ font-family: 'Noto Sans TC','Microsoft JhengHei',sans-serif; max-width: 980px;
         margin: 24px auto; padding: 0 20px; color: #1f2937; }}
  .hdr {{ display:flex; justify-content:space-between; align-items:flex-end;
         border-bottom: 2px solid #1f2937; padding-bottom:8px; margin-bottom:16px; }}
  .hdr h1 {{ margin:0; font-size: 22px; }}
  .meta {{ font-size: 12px; color:#6b7280; text-align: right; }}
  .summary {{ background:#f3f4f6; padding: 10px 14px; border-radius: 6px;
              font-size: 13px; line-height: 1.6; margin-bottom: 18px; }}
  .scenarios {{ display:grid; grid-template-columns: 1fr; gap: 14px; }}
  .card {{ border: 1px solid #e5e7eb; border-left-width: 5px; border-radius: 6px; padding: 14px 18px; }}
  .card h3 {{ margin: 0 0 6px 0; font-size: 16px; }}
  .card .thesis {{ font-size: 13px; color: #374151; margin-bottom: 10px; }}
  .grid {{ display:grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }}
  .grid .k {{ font-size: 11px; color:#6b7280; }}
  .grid .v {{ font-size: 14px; font-weight: 600; }}
  .detail {{ font-size: 12px; color:#4b5563; margin-top: 10px; line-height: 1.7; }}
  .detail b {{ color: #1f2937; }}
  .disclaimer {{ font-size: 10px; color:#9ca3af; margin-top: 20px;
                 border-top:1px dashed #e5e7eb; padding-top: 6px; }}
  .print-btn {{ font-size: 12px; padding: 4px 10px; border-radius: 4px;
                background: #1f2937; color: white; border: none; cursor: pointer; }}
</style>
</head>
<body>

<div class="hdr">
  <div>
    <h1>{snap.stock_id} {snap.stock_name} ・ 三情境交易計畫</h1>
  </div>
  <div class="meta">
    Bull / Bear / Base ・ 資料截止 {snap.as_of} ・ 產出 {today_str()}
    <br><button class="print-btn no-print" onclick="window.print()">列印 / 存成 PDF</button>
  </div>
</div>

<div class="summary">
  <b>現價：</b> NT$ {fmt_num(snap.close)} ・
  <b>結構：</b> {trend} ・
  <b>20D 區間：</b> NT$ {fmt_num(snap.low_20)} – NT$ {fmt_num(snap.high_20)} ・
  <b>ATR14：</b> {fmt_num(snap.atr14, 2)} ・
  <b>RSI14：</b> {fmt_num(snap.rsi14, 1)}<br>
  <span style="display:inline-block;margin-top:6px;">{spark_svg}</span>
  <span style="margin-left:8px;color:#6b7280;font-size:11px;">近 120 日收盤走勢</span>
</div>

<div class="scenarios">
  {cards_html}
</div>

<div class="disclaimer">{report_disclaimer()}</div>

</body>
</html>"""


def _scenario_card(s: dict) -> str:
    rr = f"{s['rr']:.2f}x" if s.get("rr") else "—"
    t2 = "" if not s.get("target1") else f"<br><b>目標 1：</b> NT$ {fmt_num(s['target1'])}"
    t3 = "" if not s.get("target2") else f"<br><b>目標 2：</b> NT$ {fmt_num(s['target2'])}"
    return f"""
<div class="card" style="border-left-color: {s['color']};">
  <h3 style="color:{s['color']};">{s['name']}</h3>
  <div class="thesis">{s['thesis']}</div>
  <div class="grid">
    <div><div class="k">進場參考</div><div class="v">NT$ {fmt_num(s['entry'])}</div></div>
    <div><div class="k">停損</div><div class="v">NT$ {fmt_num(s['stop'])}</div></div>
    <div><div class="k">目標</div><div class="v">NT$ {fmt_num(s['target1'])}</div></div>
    <div><div class="k">風報比 (R:R)</div><div class="v">{rr}</div></div>
  </div>
  <div class="detail">
    <b>觸發條件：</b> {s['trigger']}<br>
    <b>持有期：</b> {s['horizon']}{t3}<br>
    <b>可能催化劑：</b> {s['catalyst']}<br>
    <b>失效訊號：</b> {s['invalidate']}<br>
    <b>部位管理：</b> {s['size']}
  </div>
</div>
"""
