from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import feedparser
import requests

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

# Maps NSE/BSE ticker symbols to the company's full search name.
# More specific queries = more relevant and timely results from Google News.
TICKER_TO_COMPANY: dict[str, str] = {
    "RELIANCE": "Reliance Industries",
    "TCS": "Tata Consultancy Services",
    "INFY": "Infosys",
    "HDFCBANK": "HDFC Bank",
    "ICICIBANK": "ICICI Bank",
    "HINDUNILVR": "Hindustan Unilever",
    "SBIN": "State Bank of India",
    "BAJFINANCE": "Bajaj Finance",
    "BHARTIARTL": "Bharti Airtel",
    "KOTAKBANK": "Kotak Mahindra Bank",
    "LT": "Larsen Toubro",
    "AXISBANK": "Axis Bank",
    "ASIANPAINT": "Asian Paints",
    "MARUTI": "Maruti Suzuki",
    "SUNPHARMA": "Sun Pharmaceutical",
    "TITAN": "Titan Company",
    "WIPRO": "Wipro",
    "TECHM": "Tech Mahindra",
    "HCLTECH": "HCL Technologies",
    "ULTRACEMCO": "UltraTech Cement",
    "NESTLEIND": "Nestle India",
    "ADANIENT": "Adani Enterprises",
    "ADANIPORTS": "Adani Ports",
    "POWERGRID": "Power Grid Corporation",
    "NTPC": "NTPC",
    "ONGC": "ONGC",
    "COALINDIA": "Coal India",
    "BPCL": "BPCL",
    "DIVISLAB": "Divi's Laboratories",
    "DRREDDY": "Dr Reddy's Laboratories",
    "CIPLA": "Cipla",
    "GRASIM": "Grasim Industries",
    "EICHERMOT": "Eicher Motors",
    "BAJAJ-AUTO": "Bajaj Auto",
    "HEROMOTOCO": "Hero MotoCorp",
    "M&M": "Mahindra Mahindra",
    "TATACONSUM": "Tata Consumer Products",
    "BRITANNIA": "Britannia Industries",
    "HINDALCO": "Hindalco Industries",
    "TATASTEEL": "Tata Steel",
    "JSWSTEEL": "JSW Steel",
    "INDUSINDBK": "IndusInd Bank",
    "SBILIFE": "SBI Life Insurance",
    "HDFCLIFE": "HDFC Life Insurance",
    "ICICIGI": "ICICI Lombard",
    "ITC": "ITC",
    "PIDILITIND": "Pidilite Industries",
    "HAVELLS": "Havells India",
    "SIEMENS": "Siemens India",
    "ABB": "ABB India",
    "IRCTC": "IRCTC",
    "DMART": "Avenue Supermarts DMart",
    "ZOMATO": "Zomato",
    "NYKAA": "Nykaa FSN E-Commerce",
    "PAYTM": "Paytm One97 Communications",
    "POLICYBZR": "PB Fintech PolicyBazaar",
    "MAPMYINDIA": "MapMyIndia CE Info Systems",
}


def _search_term(ticker: str) -> str:
    return TICKER_TO_COMPANY.get(ticker.upper(), ticker)


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
