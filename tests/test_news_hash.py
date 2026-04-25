from src.bot import _news_hash
from src.news_fetcher import NewsItem


def test_news_hash_stable() -> None:
    item = NewsItem(
        ticker="INFY",
        title="Infosys wins major deal",
        url="https://example.com/news",
        source="Example",
        published_at="2026-04-25T10:00:00+00:00",
    )
    assert _news_hash(item) == _news_hash(item)
