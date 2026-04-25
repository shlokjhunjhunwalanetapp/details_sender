from __future__ import annotations

from src.fundamentals_fetcher import DEFAULT_FIELDS, StockFundamentals


def render_fundamentals_table(fundamentals: StockFundamentals) -> str:
    lines = [f"{fundamentals.ticker} Fundamentals", "Metric | Value", "---|---"]
    for key in DEFAULT_FIELDS:
        lines.append(f"{key} | {fundamentals.metrics.get(key, 'N/A')}")
    return "\n".join(lines)
