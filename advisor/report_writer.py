from pathlib import Path


def _fmt_percent(value: float | int | None) -> str:
    if value is None:
        return "N/A"
    return f"{float(value) * 100:.2f}%"


def write_markdown_report(report: dict, output_path: str) -> None:
    """Write a markdown decision-support report."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    technical = report.get("technical", {})
    backtest = report.get("backtest", {})
    market = report.get("market", {})
    chip = report.get("chip", {})
    risks = report.get("risks", [])

    lines = [
        f"# {report.get('stock_id', '')} {report.get('stock_name', '')} 決策輔助報告",
        "",
        "## 策略",
        f"{report.get('strategy_display') or report.get('strategy_name', '')}",
        "",
        "## 技術面",
        f"- 訊號日期：{report.get('signal_date', '')}",
        f"- 收盤價：{technical.get('close', 'N/A')}",
        f"- RSI14：{technical.get('rsi14', 'N/A')}",
        f"- 技術分數：{technical.get('technical_score', 'N/A')}",
        f"- 理由：{technical.get('reason', '')}",
        "",
        "## 回測結果",
        f"- 樣本數：{backtest.get('trade_count', 0)}",
        f"- 勝率：{_fmt_percent(backtest.get('win_rate'))}",
        f"- 平均淨報酬：{_fmt_percent(backtest.get('avg_return'))}",
        f"- 最大回撤：{_fmt_percent(backtest.get('max_drawdown'))}",
        "",
        "## 籌碼",
        chip.get("summary", "第一版尚未接籌碼資料。"),
        "",
        "## 大盤環境",
        market.get("summary", ""),
        "",
        "## 風險",
    ]
    lines.extend([f"- {risk}" for risk in risks])
    lines.extend(
        [
            "",
            "## 結論",
            report.get("suggestion", "觀察，等待更多確認。"),
            "",
            "> 本報告僅供策略研究與決策輔助，不構成投資建議。",
        ]
    )

    path.write_text("\n".join(lines), encoding="utf-8")
