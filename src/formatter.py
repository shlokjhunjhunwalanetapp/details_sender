from __future__ import annotations

from collections import defaultdict

from src.fundamentals_fetcher import DEFAULT_FIELDS, StockFundamentals
from src.verifier import VerifiedNews


def render_fundamentals_table(fundamentals: StockFundamentals) -> str:
    lines = [f"{fundamentals.ticker} Fundamentals", "Metric | Value", "---|---"]
    for key in DEFAULT_FIELDS:
        lines.append(f"{key} | {fundamentals.metrics.get(key, 'N/A')}")
    return "\n".join(lines)


def render_news_digest(verified: list[VerifiedNews]) -> str:
    if not verified:
        return "No recent news found."

    grouped: dict[str, list[VerifiedNews]] = defaultdict(list)
    for item in verified:
        grouped[item.ticker].append(item)

    lines: list[str] = []
    for ticker in sorted(grouped):
        lines.append(f"{ticker} News Verification")
        for item in grouped[ticker][:4]:
            lines.append(
                f"- [{item.verdict}:{item.authenticity_score}] {item.title} ({item.source})\n"
                f"  {item.reason}\n"
                f"  {item.url}"
            )
        lines.append("")
    return "\n".join(lines).strip()
