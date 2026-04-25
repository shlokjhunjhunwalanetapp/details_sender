from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from src.bot import _is_market_hours, _interval_lower_bound, _published_after
from src.config import Config
from src.news_fetcher import NewsItem


def _config() -> Config:
    return Config(
        telegram_bot_token="x",
        telegram_chat_id="1",
        max_news_per_stock=6,
        news_recent_hours=24,
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


def test_interval_lower_bound_uses_last_cycle() -> None:
    now_utc = datetime(2026, 4, 27, 10, 0, tzinfo=timezone.utc)
    last = datetime(2026, 4, 27, 9, 55, tzinfo=timezone.utc).isoformat()
    lb = _interval_lower_bound(last, fallback_hours=24, now_utc=now_utc)
    assert lb == datetime(2026, 4, 27, 9, 55, tzinfo=timezone.utc)


def test_interval_lower_bound_falls_back_on_empty() -> None:
    now_utc = datetime(2026, 4, 27, 10, 0, tzinfo=timezone.utc)
    lb = _interval_lower_bound("", fallback_hours=24, now_utc=now_utc)
    assert lb == datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)


def _make_item(published_at: str) -> NewsItem:
    return NewsItem(
        ticker="TEST",
        title="headline",
        url="https://example.com",
        source="Reuters",
        published_at=published_at,
    )


def test_published_after_returns_true_for_newer_item() -> None:
    lower = datetime(2026, 4, 27, 9, 55, tzinfo=timezone.utc)
    item = _make_item("2026-04-27T10:00:00+00:00")
    assert _published_after(item, lower) is True


def test_published_after_returns_false_for_older_item() -> None:
    lower = datetime(2026, 4, 27, 9, 55, tzinfo=timezone.utc)
    item = _make_item("2026-04-27T09:50:00+00:00")
    assert _published_after(item, lower) is False
