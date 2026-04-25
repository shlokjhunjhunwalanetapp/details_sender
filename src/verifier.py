from __future__ import annotations

import json
from dataclasses import dataclass

import requests

from src.news_fetcher import NewsItem


@dataclass
class VerifiedNews:
    ticker: str
    title: str
    url: str
    source: str
    authenticity_score: int
    verdict: str
    confidence: str
    reason: str


def verify_news_batch(
    api_key: str,
    model: str,
    items: list[NewsItem],
    timeout: int = 45,
) -> list[VerifiedNews]:
    if not items:
        return []

    payload_items = [
        {
            "ticker": item.ticker,
            "title": item.title,
            "url": item.url,
            "source": item.source,
            "published_at": item.published_at,
        }
        for item in items
    ]
    prompt = (
        "You are a financial-news verifier. Score each news item for authenticity.\n"
        "Use source quality, language quality, and consistency with other items in the same batch.\n"
        "Return ONLY valid JSON array where each item has:\n"
        "ticker,title,url,source,authenticity_score(0-100),verdict,confidence,reason.\n"
        "Set verdict to one of: likely_true, uncertain, likely_false.\n"
        f"News items:\n{json.dumps(payload_items, ensure_ascii=True)}"
    )

    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2},
    }
    response = requests.post(endpoint, json=body, timeout=timeout)
    response.raise_for_status()
    raw = response.json()
    text = raw["candidates"][0]["content"]["parts"][0]["text"]

    # Gemini sometimes returns code fences even when asked for pure JSON.
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    parsed = json.loads(text)

    verified: list[VerifiedNews] = []
    for item in parsed:
        verified.append(
            VerifiedNews(
                ticker=str(item.get("ticker", "")),
                title=str(item.get("title", "")),
                url=str(item.get("url", "")),
                source=str(item.get("source", "")),
                authenticity_score=int(item.get("authenticity_score", 0)),
                verdict=str(item.get("verdict", "uncertain")),
                confidence=str(item.get("confidence", "low")),
                reason=str(item.get("reason", "")),
            )
        )
    return verified
