from datetime import datetime, time
from zoneinfo import ZoneInfo

from src.bot import _is_market_hours
from src.config import Config


def _config() -> Config:
    return Config(
        telegram_bot_token="x",
        telegram_chat_id="1",
        gemini_api_key="g",
        gemini_model="gemini-1.5-flash",
        llm_daily_cap=1500,
        max_news_per_stock=6,
        market_open=time(9, 15),
        market_close=time(15, 30),
        timezone=ZoneInfo("Asia/Kolkata"),
    )


def test_market_hours_true_weekday() -> None:
    now = datetime(2026, 4, 27, 10, 30, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert _is_market_hours(_config(), now) is True


def test_market_hours_false_weekend() -> None:
    now = datetime(2026, 4, 26, 10, 30, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert _is_market_hours(_config(), now) is False
