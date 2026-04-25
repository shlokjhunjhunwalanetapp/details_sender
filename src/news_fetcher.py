from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import feedparser
import requests

from src.ticker_registry import lookup_company_name

REQUEST_TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 (compatible; StockNewsBot/1.0; +https://github.com)"


@dataclass
class NewsItem:
    ticker: str
    title: str
    url: str
    source: str
    published_at: str  # ISO-8601 UTC


# Reputable Indian and global financial news sources.
# Matched case-insensitively against the source title returned by Google News RSS.
TRUSTED_SOURCES: frozenset[str] = frozenset(
    {
        "the economic times",
        "et markets",
        "mint",
        "livemint",
        "business standard",
        "business today",
        "financial express",
        "financialexpress.com",
        "moneycontrol",
        "moneycontrol.com",
        "ndtv profit",
        "cnbc tv18",
        "cnbc-tv18",
        "zee business",
        "the hindu businessline",
        "businessline",
        "reuters",
        "bloomberg",
        "investing.com india",
        "investing.com",
        "yahoo finance",
        "seeking alpha",
        "gurufocus",
        "tradingview",
        "markets mojo",
        "marketsmojo",
        "india today",
        "news18",
        "hindustan times",
        "times of india",
        "goodreturns",
        "the hindu",
    }
)

def _search_term(ticker: str) -> str:
    """Return the best search term for a ticker.

    Uses the live registry (full NSE equity list + yfinance fallback).
    If no company name is found (unknown ticker), appends 'NSE India'
    to narrow the Google News query and reduce false positives.
    """
    name = lookup_company_name(ticker)
    if name == ticker:
        # Company name not found — make query more specific to avoid
        # matching unrelated international tickers with the same symbol.
        return f"{ticker} NSE India"
    return name


def _to_iso8601(raw_value: str | None) -> str | None:
    if not raw_value:
        return None
    try:
        return parsedate_to_datetime(raw_value).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def _is_trusted(source: str) -> bool:
    return source.strip().lower() in TRUSTED_SOURCES


def fetch_stock_news(
    ticker: str,
    max_items: int = 6,
    since: datetime | None = None,
) -> list[NewsItem]:
    """Fetch news for a stock ticker.

    `since` is a timezone-aware UTC datetime; only articles published strictly
    after this timestamp are returned.  If omitted, articles from the last 24
    hours are returned.

    Only items from trusted financial sources are included, sorted newest-first.
    The timestamp check is the very first gate inside the feed loop.
    """
    company = _search_term(ticker)
    query = quote_plus(f'"{company}" stock')
    rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"

    # Default fallback: last 24 hours
    if since is None:
        since = datetime.now(timezone.utc) - timedelta(hours=24)

    try:
        response = requests.get(rss_url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
    except Exception:
        return []

    feed = feedparser.parse(response.text)

    items: list[NewsItem] = []
    for entry in feed.entries:
        # ── Gate 1: timestamp ────────────────────────────────────────────────
        published_at = _to_iso8601(getattr(entry, "published", None))
        if not published_at:
            continue
        try:
            pub_dt = datetime.fromisoformat(published_at)
        except ValueError:
            continue
        if pub_dt.tzinfo is None:
            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
        if pub_dt <= since:
            # Article is older than our window — skip immediately.
            continue

        # ── Gate 2: source quality ───────────────────────────────────────────
        source = ""
        if getattr(entry, "source", None):
            source = entry.source.get("title", "")
        source = source.strip() or "Unknown"
        if not _is_trusted(source):
            continue

        items.append(
            NewsItem(
                ticker=ticker,
                title=entry.title,
                url=entry.link,
                source=source,
                published_at=published_at,
            )
        )

    # Newest first so the caller always sees the freshest headlines first.
    items.sort(key=lambda n: n.published_at, reverse=True)
    return items[:max_items]
