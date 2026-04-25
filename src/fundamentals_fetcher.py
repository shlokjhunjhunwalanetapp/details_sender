from __future__ import annotations

from dataclasses import dataclass, field
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

# Quarterly P&L rows we care about (label as it appears in screener.in tbody)
QUARTERLY_ROWS = [
    "Sales",
    "Expenses",
    "Operating Profit",
    "OPM %",
    "Other Income",
    "Interest",
    "Depreciation",
    "Profit before tax",
    "Tax %",
    "Net Profit",
    "EPS in Rs",
]

# Cash-flow rows
CASHFLOW_ROWS = [
    "Cash from Operating Activity",
    "Cash from Investing Activity",
    "Cash from Financing Activity",
    "Net Cash Flow",
    "Free Cash Flow",
]


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


@dataclass
class QuarterlyTable:
    """Last N quarters of P&L data from screener.in."""
    ticker: str
    headers: list[str]            # e.g. ["Dec 2024", "Mar 2025", ...]
    rows: dict[str, list[str]]    # row_label -> list of values (aligned to headers)


@dataclass
class CashFlowTable:
    """Annual cash-flow data from screener.in."""
    ticker: str
    headers: list[str]
    rows: dict[str, list[str]]


# Only fields we can reliably populate — no N/A clutter.
DEFAULT_FIELDS: list[str] = [
    "Current Price",
    "52W High / Low",
    "50D Avg",
    "200D Avg",
    "Market Cap",
    "Stock P/E (TTM)",
    "Fwd P/E",
    "Price / Book",
    "EV / EBITDA",
    "Beta",
    "Book Value",
    "Gross Margin",
    "Operating Margin",
    "Net Margin",
    "Revenue Growth (YoY)",
    "Earnings Growth (YoY)",
    "Earnings Growth (QoQ)",
    "Dividend Yield",
    "Debt / Equity",
    "Promoter Holding",
    "Institutional Holding",
]

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


def _row_label_matches(cell_text: str, target: str) -> bool:
    """Fuzzy label match: strip trailing +/- and extra spaces."""
    return cell_text.strip().rstrip(" +").strip().lower() == target.lower()


def _parse_table(
    soup: BeautifulSoup,
    section_id: str,
    wanted_rows: list[str],
    last_n_cols: int,
) -> tuple[list[str], dict[str, list[str]]]:
    """Parse a screener.in section table. Returns (headers, rows_dict)."""
    sec = soup.find("section", id=section_id)
    if not sec:
        return [], {}
    table = sec.find("table")
    if not table:
        return [], {}

    # Headers (skip the first empty label column)
    raw_headers = [th.get_text(strip=True) for th in table.select("thead th")]
    headers = raw_headers[1:]  # drop label column
    headers = headers[-last_n_cols:]

    rows: dict[str, list[str]] = {}
    for tr in table.select("tbody tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        if not cells:
            continue
        label = cells[0].strip().rstrip("+").strip()
        for wanted in wanted_rows:
            if _row_label_matches(label, wanted):
                values = cells[1:]                      # drop label col
                values = values[-last_n_cols:]          # keep last N cols
                rows[wanted] = values
                break

    return headers, rows


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
        "Dividend Yield": (
            f"{float(info['dividendYield']):.2f}%"
            if info.get("dividendYield") not in (None, "")
            else "N/A"
        ),
        "Debt / Equity": _fmt(info.get("debtToEquity")),
        "Promoter Holding": _pct(promoter),
        "Institutional Holding": _pct(institution),
    }


def _fetch_screener_soup(ticker: str) -> BeautifulSoup | None:
    url = f"https://www.screener.in/company/{ticker}/consolidated/"
    session = _build_retry_session()
    response = session.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
    if response.status_code != 200:
        logger.warning("screener.in returned %s for %s", response.status_code, ticker)
        return None
    return BeautifulSoup(response.text, "html.parser")


def _from_screener_ratios(soup: BeautifulSoup) -> dict[str, str]:
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
    metrics: dict[str, str] = {f: "N/A" for f in DEFAULT_FIELDS}
    try:
        metrics.update(_from_yfinance(ticker))
    except Exception:
        logger.exception("yfinance fundamentals fetch failed for %s", ticker)
    try:
        soup = _fetch_screener_soup(ticker)
        if soup:
            for k, v in _from_screener_ratios(soup).items():
                if k not in metrics:
                    metrics[k] = v
    except Exception:
        logger.exception("Screener ratios fetch failed for %s", ticker)
    return StockFundamentals(ticker=ticker, metrics=metrics)


def fetch_quarterly_results(ticker: str, last_quarters: int = 6) -> QuarterlyTable | None:
    """Fetch last N quarters of P&L from screener.in. Returns None on failure."""
    try:
        soup = _fetch_screener_soup(ticker)
        if not soup:
            return None
        headers, rows = _parse_table(soup, "quarters", QUARTERLY_ROWS, last_quarters)
        if not headers:
            return None
        return QuarterlyTable(ticker=ticker, headers=headers, rows=rows)
    except Exception:
        logger.exception("Quarterly results fetch failed for %s", ticker)
        return None


def fetch_cash_flow(ticker: str, last_years: int = 5) -> CashFlowTable | None:
    """Fetch last N years of cash-flow from screener.in. Returns None on failure."""
    try:
        soup = _fetch_screener_soup(ticker)
        if not soup:
            return None
        headers, rows = _parse_table(soup, "cash-flow", CASHFLOW_ROWS, last_years)
        if not headers:
            return None
        return CashFlowTable(ticker=ticker, headers=headers, rows=rows)
    except Exception:
        logger.exception("Cash-flow fetch failed for %s", ticker)
        return None
