from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import feedparser


@dataclass
class NewsItem:
    ticker: str
    title: str
    url: str
    source: str
    published_at: str


def _to_iso8601(raw_value: str | None) -> str:
    if not raw_value:
        return datetime.now(timezone.utc).isoformat()
    try:
        return parsedate_to_datetime(raw_value).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return datetime.now(timezone.utc).isoformat()


def _is_recent(published_at: str, hours: int = 48) -> bool:
    try:
        published = datetime.fromisoformat(published_at)
    except ValueError:
        return False
    return published >= datetime.now(timezone.utc) - timedelta(hours=hours)


def fetch_stock_news(ticker: str, max_items: int = 6) -> list[NewsItem]:
    query = quote_plus(f"{ticker} stock india nse bse")
    rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
    feed = feedparser.parse(rss_url)
    items: list[NewsItem] = []

    for entry in feed.entries:
        published_at = _to_iso8601(getattr(entry, "published", None))
        if not _is_recent(published_at):
            continue
        source = ""
        if getattr(entry, "source", None):
            source = entry.source.get("title", "")
        items.append(
            NewsItem(
                ticker=ticker,
                title=entry.title,
                url=entry.link,
                source=source or "Unknown",
                published_at=published_at,
            )
        )
        if len(items) >= max_items:
            break

    return items
