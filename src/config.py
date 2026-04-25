from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")


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
        market_open = os.getenv("MARKET_OPEN", "09:15")
        market_close = os.getenv("MARKET_CLOSE", "15:30")
        open_hour, open_minute = (int(x) for x in market_open.split(":", maxsplit=1))
        close_hour, close_minute = (int(x) for x in market_close.split(":", maxsplit=1))

        return Config(
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip(),
            llm_daily_cap=int(os.getenv("LLM_DAILY_CAP", "1500")),
            max_news_per_stock=int(os.getenv("MAX_NEWS_PER_STOCK", "6")),
            market_open=time(hour=open_hour, minute=open_minute),
            market_close=time(hour=close_hour, minute=close_minute),
            timezone=IST,
        )
