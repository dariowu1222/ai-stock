"""Comp-sheet: 同業比較 Excel。

Modeled after Daloopa's `comp-sheet` skill: pick one focus stock, pull peers
from the same industry, dump their key metrics into Excel with the focus row
highlighted.

Falls back to raw .csv writing if openpyxl is unavailable, so it can ship
without forcing a new dependency.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from reports.base import (
    StockSnapshot,
    build_snapshot,
)


COMP_COLUMNS = [
    ("stock_id", "股票代號"),
    ("stock_name", "名稱"),
    ("industry", "產業"),
    ("close", "收盤"),
    ("ret_5d_pct", "5D%"),
    ("ret_20d_pct", "20D%"),
    ("ret_60d_pct", "60D%"),
    ("rsi14", "RSI14"),
    ("bias_pct", "BIAS(20)%"),
    ("ma_trend", "均線結構"),
    ("triggered_n", "今日訊號數"),
    ("triggered_list", "觸發策略"),
    ("avg_volume_20", "20日均量"),
    ("atr14", "ATR14"),
]


def generate_comp_sheet(
    focus_stock_id: str,
    stock_pool: list[dict],
    prices_by_stock: dict[str, pd.DataFrame],
    output_path: str | Path,
    *,
    peer_limit: int = 15,
) -> str:
    """Build a peer comparison Excel for the focus stock.

    - Peers = same industry_category from stock_pool (excluding focus).
    - Each row = a stock snapshot.
    - Focus row pinned to top, highlighted.
    """

    focus_meta = _find_stock(stock_pool, focus_stock_id)
    if not focus_meta:
        raise ValueError(f"Focus stock {focus_stock_id} not found in stock pool")

    focus_industry = (focus_meta.get("industry_category") or "").strip()
    peers = [
        s for s in stock_pool
        if (s.get("industry_category") or "").strip() == focus_industry
        and str(s.get("stock_id")) != str(focus_stock_id)
    ]
    # cap peer count, prefer those we have price data for
    peers = [s for s in peers if str(s.get("stock_id")) in prices_by_stock][:peer_limit]

    rows = [_row_for_stock(focus_meta, prices_by_stock.get(str(focus_stock_id)), is_focus=True)]
    for peer in peers:
        rows.append(_row_for_stock(peer, prices_by_stock.get(str(peer.get("stock_id")))))

    rows = [r for r in rows if r is not None]
    df = pd.DataFrame(rows)
    # sort peers (skip focus row at index 0) by 20D return descending
    if len(df) > 1:
        focus_row = df.iloc[[0]]
        rest = df.iloc[1:].sort_values("ret_20d_pct", ascending=False, na_position="last")
        df = pd.concat([focus_row, rest], ignore_index=True)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        _write_xlsx(df, path, focus_stock_id, focus_industry)
        return str(path)
    except ImportError:
        # openpyxl missing — fall back to CSV
        csv_path = path.with_suffix(".csv")
        _write_csv(df, csv_path)
        return str(csv_path)


def _row_for_stock(meta: dict, prices: pd.DataFrame | None, *, is_focus: bool = False) -> dict | None:
    stock_id = str(meta.get("stock_id", "")).strip()
    if not stock_id:
        return None
    if prices is None or prices.empty:
        return {
            "stock_id": stock_id,
            "stock_name": meta.get("stock_name", ""),
            "industry": meta.get("industry_category", ""),
            "close": None,
            "ret_5d_pct": None,
            "ret_20d_pct": None,
            "ret_60d_pct": None,
            "rsi14": None,
            "bias_pct": None,
            "ma_trend": "資料不足",
            "triggered_n": 0,
            "triggered_list": "",
            "avg_volume_20": None,
            "atr14": None,
            "is_focus": is_focus,
        }
    try:
        snap = build_snapshot(
            stock_id,
            meta.get("stock_name", ""),
            meta.get("industry_category", ""),
            meta.get("market", ""),
            prices,
        )
    except Exception:
        return None
    return {
        "stock_id": snap.stock_id,
        "stock_name": snap.stock_name,
        "industry": snap.industry,
        "close": round(snap.close, 2),
        "ret_5d_pct": round(snap.ret_5d * 100, 2),
        "ret_20d_pct": round(snap.ret_20d * 100, 2),
        "ret_60d_pct": round(snap.ret_60d * 100, 2),
        "rsi14": round(snap.rsi14, 1) if not pd.isna(snap.rsi14) else None,
        "bias_pct": round(snap.bias * 100, 2) if not pd.isna(snap.bias) else None,
        "ma_trend": _trend(snap),
        "triggered_n": len(snap.triggered_strategies),
        "triggered_list": ", ".join(snap.triggered_strategies),
        "avg_volume_20": int(snap.avg_volume_20) if not pd.isna(snap.avg_volume_20) else None,
        "atr14": round(snap.atr14, 2) if not pd.isna(snap.atr14) else None,
        "is_focus": is_focus,
    }


def _trend(snap: StockSnapshot) -> str:
    if pd.isna(snap.ma5) or pd.isna(snap.ma20) or pd.isna(snap.ma60):
        return "—"
    if snap.ma5 > snap.ma20 > snap.ma60:
        return "多頭"
    if snap.ma5 < snap.ma20 < snap.ma60:
        return "空頭"
    return "盤整"


def _find_stock(stock_pool: list[dict], stock_id: str) -> dict | None:
    for s in stock_pool:
        if str(s.get("stock_id", "")).strip() == str(stock_id).strip():
            return s
    return None


def _write_xlsx(df: pd.DataFrame, path: Path, focus_id: str, focus_industry: str) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Comp Sheet"

    # Title row
    ws.cell(row=1, column=1, value=f"同業比較 ・ Focus: {focus_id} ・ 產業: {focus_industry or '—'}")
    ws.cell(row=1, column=1).font = Font(size=14, bold=True)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(COMP_COLUMNS))

    # Header
    header_fill = PatternFill("solid", fgColor="1F2937")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    for col_idx, (_, label) in enumerate(COMP_COLUMNS, start=1):
        cell = ws.cell(row=3, column=col_idx, value=label)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    # Body
    focus_fill = PatternFill("solid", fgColor="FFF7CC")
    multi_signal_font = Font(color="15803D", bold=True)

    for row_idx, record in enumerate(df.to_dict("records"), start=4):
        for col_idx, (key, _) in enumerate(COMP_COLUMNS, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=record.get(key))
            if record.get("is_focus"):
                cell.fill = focus_fill
                if col_idx == 1:
                    cell.font = Font(bold=True)
            if key == "triggered_n" and (record.get(key) or 0) >= 2:
                cell.font = multi_signal_font

    # Auto-width
    for col_idx, (key, _) in enumerate(COMP_COLUMNS, start=1):
        max_len = len(COMP_COLUMNS[col_idx - 1][1])
        for record in df.to_dict("records"):
            val = record.get(key)
            if val is not None:
                max_len = max(max_len, len(str(val)))
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 2, 24)

    # Notes
    notes_row = ws.max_row + 2
    ws.cell(row=notes_row, column=1, value="說明：黃底為 focus 個股；訊號數 ≥ 2 以綠字標示；同業排序依 20D% 由高到低。")
    ws.cell(row=notes_row, column=1).font = Font(italic=True, color="6B7280", size=10)
    ws.merge_cells(start_row=notes_row, start_column=1, end_row=notes_row, end_column=len(COMP_COLUMNS))

    ws.cell(row=notes_row + 1, column=1, value="本報告由 AI 台股工具自動生成，僅供研究與決策輔助，不構成投資建議。")
    ws.cell(row=notes_row + 1, column=1).font = Font(italic=True, color="9CA3AF", size=9)
    ws.merge_cells(start_row=notes_row + 1, start_column=1, end_row=notes_row + 1, end_column=len(COMP_COLUMNS))

    wb.save(path)


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    export = df.copy()
    if "is_focus" in export.columns:
        export = export.drop(columns=["is_focus"])
    export.to_csv(path, index=False, encoding="utf-8-sig")
