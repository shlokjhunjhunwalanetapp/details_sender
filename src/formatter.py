from __future__ import annotations

from src.fundamentals_fetcher import (
    CashFlowTable,
    DEFAULT_FIELDS,
    QuarterlyTable,
    StockFundamentals,
)


def render_fundamentals_table(fundamentals: StockFundamentals) -> str:
    lines = [f"{fundamentals.ticker} Fundamentals", "Metric | Value", "---|---"]
    for key in DEFAULT_FIELDS:
        lines.append(f"{key} | {fundamentals.metrics.get(key, 'N/A')}")
    return "\n".join(lines)


def _compact_table(
    title: str,
    headers: list[str],
    rows: dict[str, list[str]],
    row_order: list[str],
    unit_note: str = "",
) -> str:
    """Render a multi-column table as monospaced text suitable for Telegram."""
    if not headers or not rows:
        return ""

    # Shorten quarter/year labels: "Dec 2024" -> "Dec'24", "Mar 2025" -> "Mar'25"
    short_headers = [
        h[:3] + "'" + h[-2:] if len(h) >= 7 else h
        for h in headers
    ]

    label_col_w = max((len(r) for r in row_order if r in rows), default=10) + 1
    col_w = max(max((len(v) for v in vals), default=4) for vals in rows.values())
    col_w = max(col_w, max(len(h) for h in short_headers)) + 1

    header_line = " " * label_col_w + "  ".join(h.rjust(col_w) for h in short_headers)
    sep = "-" * len(header_line)

    lines = [f"{title}"]
    if unit_note:
        lines.append(unit_note)
    lines += [header_line, sep]

    for row_label in row_order:
        if row_label not in rows:
            continue
        vals = rows[row_label]
        padded_vals = "  ".join(v.rjust(col_w) for v in vals)
        lines.append(f"{row_label:<{label_col_w}}{padded_vals}")

    return "\n".join(lines)


def render_quarterly_results(table: QuarterlyTable) -> str:
    from src.fundamentals_fetcher import QUARTERLY_ROWS
    return _compact_table(
        title=f"{table.ticker} — Quarterly Results (Consolidated, ₹ Cr)",
        headers=table.headers,
        rows=table.rows,
        row_order=QUARTERLY_ROWS,
        unit_note="Figures in Rs. Crores",
    )


def render_cash_flow(table: CashFlowTable) -> str:
    from src.fundamentals_fetcher import CASHFLOW_ROWS
    return _compact_table(
        title=f"{table.ticker} — Cash Flow (₹ Cr)",
        headers=table.headers,
        rows=table.rows,
        row_order=CASHFLOW_ROWS,
        unit_note="Figures in Rs. Crores",
    )
