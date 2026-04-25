from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")


def _safe_int(value: str, default: int, *, minimum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(parsed, minimum)


def _safe_time(value: str, default: str) -> time:
    candidate = value or default
    try:
        hour_str, minute_str = candidate.split(":", maxsplit=1)
        hour = int(hour_str)
        minute = int(minute_str)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("out of range")
        return time(hour=hour, minute=minute)
    except (AttributeError, ValueError):
        default_hour_str, default_minute_str = default.split(":", maxsplit=1)
        return time(hour=int(default_hour_str), minute=int(default_minute_str))


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    telegram_chat_id: str
    gemini_api_key: str
    gemini_model: str
    llm_daily_cap: int
    max_news_per_stock: int
    market_open: time
    market_close: time
    timezone: ZoneInfo

    @staticmethod
    def from_env() -> "Config":
        return Config(
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip(),
            llm_daily_cap=_safe_int(os.getenv("LLM_DAILY_CAP", "1500"), 1500, minimum=1),
            max_news_per_stock=_safe_int(os.getenv("MAX_NEWS_PER_STOCK", "6"), 6, minimum=1),
            market_open=_safe_time(os.getenv("MARKET_OPEN", "09:15"), "09:15"),
            market_close=_safe_time(os.getenv("MARKET_CLOSE", "15:30"), "15:30"),
            timezone=IST,
        )
