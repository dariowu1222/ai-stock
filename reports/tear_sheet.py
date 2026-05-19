"""Tear-sheet: 一頁紙個股研報（HTML 輸出）。

Modeled after S&P Global's `tear-sheet` skill: same data, three audience modes
(retail / self-trade / pro) produce different tone & detail.

Inputs are existing project objects only — no external API calls.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from reports.base import (
    AUDIENCE_LABELS,
    AUDIENCE_PRO,
    AUDIENCE_RETAIL,
    AUDIENCE_SELF_TRADE,
    StockSnapshot,
    build_snapshot,
    fmt_int,
    fmt_num,
    fmt_pct,
    momentum_label,
    report_disclaimer,
    sparkline_svg,
    today_str,
    trend_label,
)
from strategy.templates import get_strategy_template


def generate_tear_sheet(
    stock_id: str,
    stock_name: str,
    industry: str,
    market: str,
    prices: pd.DataFrame,
    output_path: str | Path,
    *,
    audience: str = AUDIENCE_SELF_TRADE,
) -> str:
    """Render a single-page HTML tear-sheet. Returns absolute output path."""

    snap = build_snapshot(stock_id, stock_name, industry, market, prices)
    spark_values = prices.sort_values("date")["close"].tail(90).tolist()

    html = _render_html(snap, spark_values, audience)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return str(path)


# ------------ rendering ------------


def _render_html(snap: StockSnapshot, spark_values: list[float], audience: str) -> str:
    audience_label = AUDIENCE_LABELS.get(audience, audience)
    spark = sparkline_svg(spark_values, width=320, height=64)
    narrative = _audience_narrative(snap, audience)
    risk_block = _risk_block(snap)
    technical_block = _technical_block(snap)
    signal_block = _signal_block(snap)
    appendix = _appendix_block(snap) if audience == AUDIENCE_PRO else ""

    daily_color = "#15803d" if snap.daily_change_pct >= 0 else "#b91c1c"

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<title>{snap.stock_id} {snap.stock_name} Tear Sheet</title>
<style>
  body {{ font-family: 'Noto Sans TC', 'Microsoft JhengHei', sans-serif;
         max-width: 920px; margin: 24px auto; padding: 0 20px; color: #1f2937; }}
  .hdr {{ display:flex; justify-content:space-between; align-items:flex-end;
         border-bottom: 2px solid #1f2937; padding-bottom: 8px; margin-bottom: 16px; }}
  .hdr h1 {{ margin:0; font-size: 22px; }}
  .hdr .meta {{ font-size: 12px; color: #6b7280; text-align: right; }}
  .badge {{ display:inline-block; background:#eef2ff; color:#3730a3;
            padding:2px 10px; border-radius:10px; font-size:12px; margin-left:6px; }}
  .row {{ display:flex; gap:16px; margin-bottom: 18px; flex-wrap: wrap; }}
  .card {{ flex:1; min-width: 200px; background:#f9fafb; padding:12px 16px; border-radius:8px;
           border: 1px solid #e5e7eb; }}
  .card .label {{ font-size: 11px; color:#6b7280; }}
  .card .value {{ font-size: 20px; font-weight: 600; margin-top:2px; }}
  .card.big {{ flex: 2; }}
  h2 {{ font-size: 14px; margin: 18px 0 8px; padding-bottom:4px; border-bottom: 1px solid #e5e7eb;
        color: #374151; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  td, th {{ padding: 6px 8px; border-bottom: 1px solid #f3f4f6; text-align: left; }}
  th {{ color:#6b7280; font-weight:500; font-size: 12px; }}
  .narrative {{ background:#fffbeb; border-left: 3px solid #f59e0b;
                padding: 10px 14px; border-radius: 4px; font-size: 13px; line-height: 1.7; }}
  .signal-on {{ color:#15803d; font-weight:600; }}
  .signal-off {{ color:#9ca3af; }}
  .disclaimer {{ font-size: 10px; color:#9ca3af; margin-top: 20px;
                 border-top:1px dashed #e5e7eb; padding-top: 6px; }}
</style>
</head>
<body>

<div class="hdr">
  <div>
    <h1>{snap.stock_id} {snap.stock_name}
      <span class="badge">{snap.market or '—'}</span>
      <span class="badge">{snap.industry or '—'}</span>
    </h1>
  </div>
  <div class="meta">
    Tear Sheet ・ {audience_label}<br>
    資料截止 {snap.as_of} ・ 產出 {today_str()}
  </div>
</div>

<div class="row">
  <div class="card big">
    <div class="label">收盤價 / 日漲跌</div>
    <div class="value">NT$ {fmt_num(snap.close)} <span style="font-size:14px;color:{daily_color};">({fmt_pct(snap.daily_change_pct)})</span></div>
    <div style="margin-top:8px;">{spark}</div>
    <div class="label" style="margin-top:4px;">近 90 日收盤走勢</div>
  </div>
  <div class="card">
    <div class="label">5 / 20 / 60 日報酬</div>
    <div style="font-size:14px;line-height:1.7;">
      5D: <b>{fmt_pct(snap.ret_5d)}</b><br>
      20D: <b>{fmt_pct(snap.ret_20d)}</b><br>
      60D: <b>{fmt_pct(snap.ret_60d)}</b>
    </div>
  </div>
  <div class="card">
    <div class="label">52 週區間</div>
    <div style="font-size:14px;line-height:1.7;">
      高: <b>NT$ {fmt_num(snap.high_52w)}</b><br>
      低: <b>NT$ {fmt_num(snap.low_52w)}</b>
    </div>
  </div>
</div>

<h2>結論 ・ {audience_label}</h2>
<div class="narrative">{narrative}</div>

{technical_block}

{signal_block}

{risk_block}

{appendix}

<div class="disclaimer">{report_disclaimer()}</div>

</body>
</html>"""


def _technical_block(snap: StockSnapshot) -> str:
    return f"""
<h2>技術面快照</h2>
<table>
  <tr>
    <th>趨勢</th><td>{trend_label(snap)}（MA5 {fmt_num(snap.ma5)} / MA20 {fmt_num(snap.ma20)} / MA60 {fmt_num(snap.ma60)}）</td>
    <th>動能</th><td>{momentum_label(snap)} （RSI14 {fmt_num(snap.rsi14, 1)}）</td>
  </tr>
  <tr>
    <th>MACD</th><td>hist {fmt_num(snap.macd_hist, 3)} ・ macd {fmt_num(snap.macd, 3)}</td>
    <th>KD</th><td>K {fmt_num(snap.k, 1)} / D {fmt_num(snap.d, 1)}</td>
  </tr>
  <tr>
    <th>BIAS(20)</th><td>{fmt_pct(snap.bias)}（負值偏弱、正值偏強）</td>
    <th>ATR14</th><td>{fmt_num(snap.atr14, 2)} 元 / 日</td>
  </tr>
  <tr>
    <th>20 日高 / 低</th><td>{fmt_num(snap.high_20)} / {fmt_num(snap.low_20)}</td>
    <th>當日量 / 20 日均量</th><td>{fmt_int(snap.volume)} / {fmt_int(snap.avg_volume_20)}</td>
  </tr>
</table>
"""


def _signal_block(snap: StockSnapshot) -> str:
    from strategy.templates import list_strategy_templates

    rows = []
    triggered_set = set(snap.triggered_strategies)
    for tpl in list_strategy_templates():
        on = tpl["strategy_name"] in triggered_set
        flag = '<span class="signal-on">● 觸發</span>' if on else '<span class="signal-off">○ 未觸發</span>'
        rows.append(
            f"<tr><td>{flag}</td><td><b>{tpl['display_name']}</b></td>"
            f"<td style='color:#6b7280;font-size:12px;'>{tpl['description']}</td></tr>"
        )
    return f"""
<h2>策略訊號（今日狀態）</h2>
<table>{''.join(rows)}</table>
"""


def _risk_block(snap: StockSnapshot) -> str:
    if pd.isna(snap.atr14) or snap.atr14 == 0:
        stop_atr_2 = "—"
        stop_atr_1 = "—"
    else:
        stop_atr_2 = f"NT$ {fmt_num(snap.close - 2 * snap.atr14)}"
        stop_atr_1 = f"NT$ {fmt_num(snap.close - 1 * snap.atr14)}"
    return f"""
<h2>風控參考</h2>
<table>
  <tr><th>ATR×1 停損（短線）</th><td>{stop_atr_1}（距現價約 {fmt_pct(snap.atr14 / snap.close if snap.close else 0)}）</td></tr>
  <tr><th>ATR×2 停損（波段）</th><td>{stop_atr_2}</td></tr>
  <tr><th>20 日低點停損</th><td>NT$ {fmt_num(snap.low_20)}</td></tr>
  <tr><th>建議單筆風險</th><td>單筆部位風險 ≤ 總資金 1–2%；以 ATR 推算部位大小</td></tr>
</table>
"""


def _appendix_block(snap: StockSnapshot) -> str:
    """Pro audience only — fundamentals placeholder + raw indicator dump."""
    return f"""
<h2>附錄（法人模式）</h2>
<table>
  <tr><th>基本面（v2 接 FinMind）</th>
      <td>月營收 YoY / EPS / PE / PB / 殖利率 — <i>尚未接入</i></td></tr>
  <tr><th>籌碼面（v2 接 FinMind）</th>
      <td>三大法人買賣超 / 融資餘額 / 借券賣出 — <i>尚未接入</i></td></tr>
  <tr><th>原始指標 dump</th>
      <td style="font-family:monospace;font-size:11px;">
        close={snap.close} ・ ma5={snap.ma5:.3f} ・ ma20={snap.ma20:.3f} ・ ma60={snap.ma60:.3f}<br>
        rsi14={snap.rsi14:.3f} ・ macd={snap.macd:.3f} ・ macd_hist={snap.macd_hist:.3f}<br>
        k={snap.k:.3f} ・ d={snap.d:.3f} ・ bias={snap.bias:.4f} ・ atr14={snap.atr14:.3f}
      </td></tr>
</table>
"""


def _audience_narrative(snap: StockSnapshot, audience: str) -> str:
    trend = trend_label(snap)
    momentum = momentum_label(snap)
    triggered_n = len(snap.triggered_strategies)
    triggered_disp = "、".join(
        get_strategy_template(s)["display_name"] for s in snap.triggered_strategies
    ) or "—"

    if audience == AUDIENCE_RETAIL:
        if triggered_n == 0:
            verdict = "今日沒有特別的買訊；不急著進場。"
        elif trend == "多頭排列":
            verdict = f"目前 {trend}，出現 {triggered_n} 個策略訊號（{triggered_disp}）。可列入觀察，不要追高。"
        else:
            verdict = f"出現 {triggered_n} 個策略訊號（{triggered_disp}），但趨勢 {trend}，先觀察、等回穩。"
        return (
            f"<b>一句話：</b> {verdict}<br>"
            f"<b>近況：</b> 20 日報酬 {fmt_pct(snap.ret_20d)}、{momentum}。<br>"
            f"<b>風險提醒：</b> 跌破 NT$ {fmt_num(snap.low_20)}（20 日低）或 ATR 停損點要嚴守。"
        )

    if audience == AUDIENCE_SELF_TRADE:
        if triggered_n == 0:
            entry = "今日無訊號，等待觸發再進場。"
        else:
            entry = f"今日觸發：{triggered_disp}（{triggered_n} 個）。可考慮明日開盤或盤中突破 NT$ {fmt_num(snap.high_20)} 進場。"
        stop = "—" if pd.isna(snap.atr14) else f"NT$ {fmt_num(snap.close - 2 * snap.atr14)}"
        target = "—" if pd.isna(snap.atr14) else f"NT$ {fmt_num(snap.close + 3 * snap.atr14)}"
        return (
            f"<b>進場：</b> {entry}<br>"
            f"<b>停損：</b> {stop}（ATR×2）或跌破 20 日低 NT$ {fmt_num(snap.low_20)}<br>"
            f"<b>目標：</b> {target}（ATR×3）或挑戰 52 週高 NT$ {fmt_num(snap.high_52w)}<br>"
            f"<b>結構：</b> {trend} ・ {momentum} ・ BIAS {fmt_pct(snap.bias)}"
        )

    # AUDIENCE_PRO
    return (
        f"Setup: {trend}, {momentum}, 20D return {fmt_pct(snap.ret_20d)}, "
        f"BIAS {fmt_pct(snap.bias)}. "
        f"Active signals ({triggered_n}): {triggered_disp}. "
        f"Vol vs 20D avg: {snap.volume / snap.avg_volume_20:.2f}x" if snap.avg_volume_20 else
        f"Setup: {trend}, {momentum}, 20D return {fmt_pct(snap.ret_20d)}."
    )
