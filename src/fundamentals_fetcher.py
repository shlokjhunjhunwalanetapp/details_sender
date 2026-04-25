from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import yfinance as yf
from bs4 import BeautifulSoup

from src.portfolio_parser import format_ticker_for_yfinance


REQUEST_TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 (compatible; StockNewsBot/1.0; +https://github.com)"
logger = logging.getLogger(__name__)


def _build_retry_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        read=3,
        connect=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


@dataclass
class StockFundamentals:
    ticker: str
    metrics: dict[str, str]


# Only fields we can reliably populate — no N/A clutter.
DEFAULT_FIELDS: list[str] = [
    # Price
    "Current Price",
    "52W High / Low",
    "50D Avg",
    "200D Avg",
    # Valuation
    "Market Cap",
    "Stock P/E (TTM)",
    "Fwd P/E",
    "Price / Book",
    "EV / EBITDA",
    "Beta",
    # Profitability
    "Book Value",
    "Gross Margin",
    "Operating Margin",
    "Net Margin",
    # Growth
    "Revenue Growth (YoY)",
    "Earnings Growth (YoY)",
    "Earnings Growth (QoQ)",
    # Dividend & debt
    "Dividend Yield",
    "Debt / Equity",
    # Holding pattern
    "Promoter Holding",
    "Institutional Holding",
]

# Screener.in fields that supplement yfinance (only top-9 are reliably in HTML)
SCREENER_KEY_ALIASES: dict[str, str] = {
    "marketcap": "Market Cap",
    "currentprice": "Current Price",
    "highlow": "52W High / Low",
    "stockpe": "Stock P/E (TTM)",
    "bookvalue": "Book Value",
    "dividendyield": "Dividend Yield",
    "roce": "ROCE",
    "roe": "ROE",
    "facevalue": "Face Value",
}


def _pct(value: Any) -> str:
    if value in (None, "", "N/A"):
        return "N/A"
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return str(value)


def _fmt(value: Any, suffix: str = "") -> str:
    if value in (None, "", "N/A"):
        return "N/A"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(v) >= 1_000_000_000_000:
        return f"₹{v / 1_000_000_000_000:.2f}T{suffix}"
    if abs(v) >= 1_000_000_000:
        return f"₹{v / 1_000_000_000:.2f}B{suffix}"
    if abs(v) >= 1_000_000:
        return f"₹{v / 1_000_000:.2f}M{suffix}"
    return f"{v:.2f}{suffix}"


def _normalize_key(key: str) -> str:
    return "".join(ch for ch in key.lower() if ch.isalnum())


def _from_yfinance(ticker: str) -> dict[str, str]:
    yf_symbol = format_ticker_for_yfinance(ticker)
    info = yf.Ticker(yf_symbol).info

    promoter = info.get("heldPercentInsiders")
    institution = info.get("heldPercentInstitutions")

    return {
        "Current Price": _fmt(info.get("currentPrice") or info.get("regularMarketPrice")),
        "52W High / Low": (
            f"{_fmt(info.get('fiftyTwoWeekHigh'))} / {_fmt(info.get('fiftyTwoWeekLow'))}"
        ),
        "50D Avg": _fmt(info.get("fiftyDayAverage")),
        "200D Avg": _fmt(info.get("twoHundredDayAverage")),
        "Market Cap": _fmt(info.get("marketCap")),
        "Stock P/E (TTM)": _fmt(info.get("trailingPE")),
        "Fwd P/E": _fmt(info.get("forwardPE")),
        "Price / Book": _fmt(info.get("priceToBook")),
        "EV / EBITDA": _fmt(info.get("enterpriseToEbitda")),
        "Beta": _fmt(info.get("beta")),
        "Book Value": _fmt(info.get("bookValue")),
        "Gross Margin": _pct(info.get("grossMargins")),
        "Operating Margin": _pct(info.get("operatingMargins")),
        "Net Margin": _pct(info.get("profitMargins")),
        "Revenue Growth (YoY)": _pct(info.get("revenueGrowth")),
        "Earnings Growth (YoY)": _pct(info.get("earningsGrowth")),
        "Earnings Growth (QoQ)": _pct(info.get("earningsQuarterlyGrowth")),
        # yfinance returns dividendYield already as a percentage for Indian stocks
        # (e.g. 0.41 means 0.41%, not 41%) — do NOT multiply by 100.
        "Dividend Yield": (
            f"{float(info['dividendYield']):.2f}%"
            if info.get("dividendYield") not in (None, "")
            else "N/A"
        ),
        "Debt / Equity": _fmt(info.get("debtToEquity")),
        "Promoter Holding": _pct(promoter),
        "Institutional Holding": _pct(institution),
    }


def _from_screener(ticker: str) -> dict[str, str]:
    """Pull screener.in top-ratios for ROCE, ROE and Face Value (not in yfinance)."""
    url = f"https://www.screener.in/company/{ticker}/consolidated/"
    session = _build_retry_session()
    response = session.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
    if response.status_code != 200:
        return {}

    soup = BeautifulSoup(response.text, "html.parser")
    kv: dict[str, str] = {}

    for li in soup.select("ul#top-ratios li.flex"):
        key_el = li.select_one("span.name")
        val_el = li.select_one("span.value")
        if not key_el or not val_el:
            continue
        key = _normalize_key(key_el.get_text(strip=True))
        mapped = SCREENER_KEY_ALIASES.get(key)
        if mapped:
            kv[mapped] = val_el.get_text(" ", strip=True)

    return kv


def fetch_fundamentals(ticker: str) -> StockFundamentals:
    metrics: dict[str, str] = {field: "N/A" for field in DEFAULT_FIELDS}
    try:
        metrics.update(_from_yfinance(ticker))
    except Exception:
        logger.exception("yfinance fundamentals fetch failed for %s", ticker)
    try:
        # Screener adds ROCE, ROE, Face Value on top of yfinance data.
        extra = _from_screener(ticker)
        for k, v in extra.items():
            if k not in metrics:
                metrics[k] = v
    except Exception:
        logger.exception("Screener fundamentals fetch failed for %s", ticker)
    return StockFundamentals(ticker=ticker, metrics=metrics)
