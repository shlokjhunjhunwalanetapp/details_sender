"""
Ticker-to-company-name registry.

Loads from data/ticker_names.json (auto-refreshed weekly by GitHub Actions).
Falls back to yfinance for any unknown ticker.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
from pathlib import Path
from typing import Any

import requests
import yfinance as yf

from src.portfolio_parser import format_ticker_for_yfinance

logger = logging.getLogger(__name__)

REGISTRY_PATH = Path("data/ticker_names.json")
REQUEST_TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 (compatible; StockNewsBot/1.0)"

# NSE index CSVs — combined gives ~1000 unique stocks covering most of the market.
NSE_INDEX_URLS = [
    "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
    "https://archives.nseindia.com/content/indices/ind_niftynext50list.csv",
    "https://archives.nseindia.com/content/indices/ind_niftymidcap150list.csv",
    "https://archives.nseindia.com/content/indices/ind_niftysmallcap250list.csv",
]

# Supplemental overrides for popular tickers not yet in any index CSV
# or where the CSV name is less recognizable than the brand name.
SUPPLEMENTAL: dict[str, str] = {
    "ZOMATO": "Zomato",
    "NYKAA": "Nykaa",
    "POLICYBZR": "PB Fintech PolicyBazaar",
    "MAPMYINDIA": "MapMyIndia",
    "DELHIVERY": "Delhivery",
    "LATENTVIEW": "Latent View Analytics",
    "TRACXN": "Tracxn Technologies",
    "IDEAFORGE": "ideaForge Technology",
    "KAYNES": "Kaynes Technology",
    "SYRMA": "Syrma SGS Technology",
    "LANDMARK": "Landmark Cars",
    "IXIGO": "Le Travenues Technology ixigo",
    "AWFIS": "Awfis Space Solutions",
    "BHARATFX": "Bharat FX",
    "SENCO": "Senco Gold",
    # Common tickers that appear with different NSE symbols in the index CSVs
    "TATAMOTORS": "Tata Motors",
    "WIPRO": "Wipro",
    "ONGC": "ONGC",
    "COALINDIA": "Coal India",
    "BPCL": "BPCL Bharat Petroleum",
    "NTPC": "NTPC",
    "GAIL": "GAIL India",
    "IOC": "Indian Oil Corporation",
    "HPCL": "Hindustan Petroleum Corporation",
    "PAYTM": "Paytm",
}

# Trailing legal-form suffixes to strip for cleaner search queries.
_SUFFIX_RE = re.compile(
    r"\s+(Ltd\.?|Limited|LTD|Pvt\.?|Corp\.?|Corporation|Inc\.?|Co\.?)\s*$",
    re.IGNORECASE,
)


def _clean(name: str) -> str:
    return _SUFFIX_RE.sub("", name.strip()).strip().rstrip(".")


def refresh_registry() -> dict[str, str]:
    """Fetch all NSE index CSVs and merge into a single registry saved to disk."""
    mapping: dict[str, str] = {}
    for url in NSE_INDEX_URLS:
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            if "Symbol" not in resp.text[:300]:
                logger.warning("Unexpected response from %s", url)
                continue
            reader = csv.DictReader(io.StringIO(resp.text))
            added = 0
            for row in reader:
                symbol = row.get("Symbol", "").strip()
                company = _clean(row.get("Company Name", "").strip())
                if symbol and company and symbol not in mapping:
                    mapping[symbol] = company
                    added += 1
            logger.info("Loaded %d tickers from %s", added, url)
        except Exception:
            logger.exception("Failed to fetch %s", url)

    # Merge supplemental overrides (brand names / recent IPOs).
    for symbol, name in SUPPLEMENTAL.items():
        mapping.setdefault(symbol, name)

    if mapping:
        REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        REGISTRY_PATH.write_text(
            json.dumps({"tickers": mapping}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        logger.info("Ticker registry refreshed: %d companies saved.", len(mapping))
    return mapping


def load_registry() -> dict[str, str]:
    """Load from disk. If missing, refresh from NSE."""
    try:
        raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        return dict(raw.get("tickers", {}))
    except (FileNotFoundError, json.JSONDecodeError):
        logger.info("Ticker registry not found on disk, fetching from NSE...")
        return refresh_registry()


def lookup_company_name(ticker: str) -> str:
    """Return the best human-readable company name for a ticker.

    Checks: registry → yfinance → ticker symbol (fallback).
    """
    registry = load_registry()
    upper = ticker.upper()

    if upper in registry:
        return registry[upper]

    # yfinance live lookup for any ticker not in Nifty 500.
    try:
        info = yf.Ticker(format_ticker_for_yfinance(ticker)).info
        name = info.get("longName") or info.get("shortName") or ""
        if name:
            cleaned = _clean(name)
            # Cache the new ticker so future lookups are instant.
            registry[upper] = cleaned
            REGISTRY_PATH.write_text(
                json.dumps({"tickers": registry}, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            logger.info("Cached new ticker %s → %s", upper, cleaned)
            return cleaned
    except Exception:
        logger.debug("yfinance lookup failed for %s", ticker)

    return ticker  # ultimate fallback: show the raw ticker
