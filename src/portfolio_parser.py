from __future__ import annotations

import re
from typing import Iterable


def _normalize_token(token: str) -> str:
    value = token.strip().upper()
    value = value.replace("$", "")
    value = re.sub(r"[^A-Z0-9\.\-]", "", value)
    return value


def parse_tickers_from_text(text: str) -> list[str]:
    body = text.strip()
    if not body:
        return []

    body = re.sub(r"^/updatestocks(@\w+)?", "", body, flags=re.IGNORECASE).strip()
    raw_parts = re.split(r"[\n,;\s]+", body)
    unique: list[str] = []
    seen: set[str] = set()
    for part in raw_parts:
        token = _normalize_token(part)
        if not token:
            continue
        if token not in seen:
            seen.add(token)
            unique.append(token)
    return unique


def format_ticker_for_yfinance(ticker: str) -> str:
    if ticker.endswith(".NS") or ticker.endswith(".BO"):
        return ticker
    return f"{ticker}.NS"


def comma_join(items: Iterable[str]) -> str:
    return ", ".join(items)
