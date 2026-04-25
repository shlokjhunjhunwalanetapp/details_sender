from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.news_fetcher import NewsItem

logger = logging.getLogger(__name__)


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


def _build_retry_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        read=3,
        connect=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"POST"}),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    return session


def _extract_text_response(raw: dict) -> str:
    candidates = raw.get("candidates") or []
    if not candidates:
        feedback = raw.get("promptFeedback", {})
        raise RuntimeError(f"Gemini returned no candidates: {feedback}")
    first = candidates[0] or {}
    parts = ((first.get("content") or {}).get("parts") or [])
    for part in parts:
        text = part.get("text")
        if text:
            return str(text)
    finish_reason = first.get("finishReason")
    raise RuntimeError(f"Gemini response contained no text parts; finishReason={finish_reason}")


def _strip_code_fences(text: str) -> str:
    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()
    return candidate


def _safe_score(value: object) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 0
    return max(0, min(100, parsed))


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
    session = _build_retry_session()
    response = session.post(endpoint, json=body, timeout=timeout)
    response.raise_for_status()
    raw = response.json()
    text = _extract_text_response(raw)

    # Gemini sometimes returns code fences even when asked for pure JSON.
    text = _strip_code_fences(text)
    parsed = json.loads(text)
    if not isinstance(parsed, list):
        raise RuntimeError("Gemini payload must be a JSON array")

    verified: list[VerifiedNews] = []
    for item in parsed:
        if not isinstance(item, dict):
            logger.warning("Skipping non-object Gemini item: %s", item)
            continue
        verified.append(
            VerifiedNews(
                ticker=str(item.get("ticker", "")),
                title=str(item.get("title", "")),
                url=str(item.get("url", "")),
                source=str(item.get("source", "")),
                authenticity_score=_safe_score(item.get("authenticity_score", 0)),
                verdict=str(item.get("verdict", "uncertain")),
                confidence=str(item.get("confidence", "low")),
                reason=str(item.get("reason", "")),
            )
        )
    return verified
