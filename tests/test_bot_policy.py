from datetime import datetime, time
from zoneinfo import ZoneInfo

from src.bot import _is_market_hours, _should_run_offhours_cycle
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


def test_offhours_cycle_first_run_allowed() -> None:
    now = datetime(2026, 4, 26, 10, 31, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert _should_run_offhours_cycle(now, "") is True


def test_offhours_cycle_requires_15_min_elapsed() -> None:
    now = datetime(2026, 4, 26, 10, 31, tzinfo=ZoneInfo("Asia/Kolkata"))
    last = datetime(2026, 4, 26, 10, 20, tzinfo=ZoneInfo("Asia/Kolkata")).isoformat()
    assert _should_run_offhours_cycle(now, last) is False

    later = datetime(2026, 4, 26, 10, 36, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert _should_run_offhours_cycle(later, last) is True
