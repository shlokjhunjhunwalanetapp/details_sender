from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
import yfinance as yf
from bs4 import BeautifulSoup

from src.portfolio_parser import format_ticker_for_yfinance


REQUEST_TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 (compatible; StockNewsBot/1.0; +https://github.com)"


@dataclass
class StockFundamentals:
    ticker: str
    metrics: dict[str, str]


DEFAULT_FIELDS: list[str] = [
    "Market Cap",
    "Current Price",
    "High / Low",
    "Stock P/E",
    "Book Value",
    "Dividend Yield",
    "ROCE",
    "ROE",
    "Face Value",
    "Promoter holding",
    "FII holding",
    "Chg in FII Hold",
    "Public holding",
    "Industry PE",
    "Chg in DII Hold",
    "Debt to equity",
    "ROE 3Yr",
    "ROE 5Yr",
    "Return over 1year",
    "Return over 3years",
    "Return over 5years",
    "Profit Var 3Yrs",
    "Profit Var 5Yrs",
    "Pledged percentage",
    "Chg in FII Hold 3Yr",
    "Chg in DII Hold 3Yr",
]


SCREENER_KEY_ALIASES: dict[str, str] = {
    "marketcap": "Market Cap",
    "currentprice": "Current Price",
    "highlow": "High / Low",
    "stockpe": "Stock P/E",
    "bookvalue": "Book Value",
    "dividendyield": "Dividend Yield",
    "roce": "ROCE",
    "roe": "ROE",
    "facevalue": "Face Value",
    "promoterholding": "Promoter holding",
    "fiiholding": "FII holding",
    "chginfiihold": "Chg in FII Hold",
    "publicholding": "Public holding",
    "industrype": "Industry PE",
    "chgindiihold": "Chg in DII Hold",
    "debttoequity": "Debt to equity",
    "roe3yr": "ROE 3Yr",
    "roe5yr": "ROE 5Yr",
    "returnover1year": "Return over 1year",
    "returnover3years": "Return over 3years",
    "returnover5years": "Return over 5years",
    "profitvar3yrs": "Profit Var 3Yrs",
    "profitvar5yrs": "Profit Var 5Yrs",
    "pledgedpercentage": "Pledged percentage",
    "chginfiihold3yrs": "Chg in FII Hold 3Yr",
    "chgindiihold3yrs": "Chg in DII Hold 3Yr",
}


def _format_number(value: Any) -> str:
    if value in (None, "", "N/A"):
        return "N/A"
    if isinstance(value, (int, float)):
        if abs(value) >= 1_000_000_000:
            return f"{value / 1_000_000_000:.2f}B"
        if abs(value) >= 1_000_000:
            return f"{value / 1_000_000:.2f}M"
        return f"{value:.2f}"
    return str(value)


def _normalize_key(key: str) -> str:
    return "".join(ch for ch in key.lower() if ch.isalnum())


def _from_yfinance(ticker: str) -> dict[str, str]:
    yf_symbol = format_ticker_for_yfinance(ticker)
    info = yf.Ticker(yf_symbol).info
    dividend = info.get("dividendYield")
    return {
        "Market Cap": _format_number(info.get("marketCap")),
        "Current Price": _format_number(info.get("currentPrice") or info.get("regularMarketPrice")),
        "High / Low": f"{_format_number(info.get('dayHigh'))} / {_format_number(info.get('dayLow'))}",
        "Stock P/E": _format_number(info.get("trailingPE")),
        "Book Value": _format_number(info.get("bookValue")),
        "Dividend Yield": _format_number(dividend * 100 if isinstance(dividend, (float, int)) else dividend),
        "Debt to equity": _format_number(info.get("debtToEquity")),
    }


def _from_screener(ticker: str) -> dict[str, str]:
    url = f"https://www.screener.in/company/{ticker}/consolidated/"
    response = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
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
    metrics = {field: "N/A" for field in DEFAULT_FIELDS}
    try:
        metrics.update(_from_yfinance(ticker))
    except Exception:
        pass
    try:
        metrics.update(_from_screener(ticker))
    except Exception:
        pass
    return StockFundamentals(ticker=ticker, metrics=metrics)
