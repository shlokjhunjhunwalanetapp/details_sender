from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.charting import create_price_charts
from src.config import Config
from src.formatter import render_fundamentals_table
from src.fundamentals_fetcher import fetch_fundamentals
from src.news_classifier import classify_headline, is_duplicate_title, title_fingerprint
from src.news_fetcher import NewsItem, fetch_stock_news
from src.portfolio_parser import comma_join, parse_tickers_from_text


logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
PORTFOLIO_PATH = DATA_DIR / "portfolio.json"
STATE_PATH = DATA_DIR / "request_budget.json"
CHART_DIR = Path("tmp/charts")


def _build_retry_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        read=3,
        connect=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class BotState:
    telegram_offset: int
    sent_hashes: list[str]
    last_full_cycle_at: str


class TelegramClient:
    def __init__(self, token: str, chat_id: str = "") -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.chat_id = chat_id
        self.session = _build_retry_session()

    @staticmethod
    def _raise_for_telegram_api(payload: dict[str, Any]) -> None:
        if not payload.get("ok", False):
            description = payload.get("description", "Unknown Telegram API error")
            raise RuntimeError(description)

    def get_updates(self, offset: int) -> list[dict[str, Any]]:
        response = self.session.get(
            f"{self.base_url}/getUpdates",
            params={"offset": offset, "timeout": 0},
            timeout=25,
        )
        response.raise_for_status()
        payload = response.json()
        self._raise_for_telegram_api(payload)
        return payload.get("result", [])

    def send_message(self, text: str, chat_id: str | None = None) -> None:
        target = chat_id or self.chat_id
        if not target:
            return
        response = self.session.post(
            f"{self.base_url}/sendMessage",
            json={"chat_id": target, "text": text, "disable_web_page_preview": True},
            timeout=25,
        )
        response.raise_for_status()
        self._raise_for_telegram_api(response.json())

    def send_photo(self, photo_path: Path, caption: str = "", chat_id: str | None = None) -> None:
        target = chat_id or self.chat_id
        if not target:
            return
        with photo_path.open("rb") as f:
            response = self.session.post(
                f"{self.base_url}/sendPhoto",
                data={"chat_id": target, "caption": caption},
                files={"photo": f},
                timeout=45,
            )
        response.raise_for_status()
        self._raise_for_telegram_api(response.json())


def _ensure_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not PORTFOLIO_PATH.exists():
        _write_json(PORTFOLIO_PATH, {"tickers": [], "updated_at": ""})
    if not STATE_PATH.exists():
        _write_json(
            STATE_PATH,
            {
                "telegram_offset": 0,
                "sent_hashes": [],
                "last_full_cycle_at": "",
            },
        )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("Invalid or missing JSON state at %s; resetting defaults", path)
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path_str = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temp_path = Path(temp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, ensure_ascii=True))
            handle.write("\n")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _load_state() -> BotState:
    raw = _read_json(STATE_PATH)
    return BotState(
        telegram_offset=max(_to_int(raw.get("telegram_offset", 0)), 0),
        sent_hashes=list(raw.get("sent_hashes", [])),
        last_full_cycle_at=str(raw.get("last_full_cycle_at", "")),
    )


def _save_state(state: BotState) -> None:
    _write_json(
        STATE_PATH,
        {
            "telegram_offset": state.telegram_offset,
            "sent_hashes": state.sent_hashes[-1000:],
            "last_full_cycle_at": state.last_full_cycle_at,
        },
    )


def _portfolio() -> list[str]:
    raw = _read_json(PORTFOLIO_PATH)
    return list(raw.get("tickers", []))


def _save_portfolio(tickers: list[str]) -> None:
    _write_json(
        PORTFOLIO_PATH,
        {"tickers": tickers, "updated_at": datetime.utcnow().isoformat()},
    )


def _is_market_hours(config: Config, now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    current_time = now.time()
    return config.market_open <= current_time <= config.market_close


def _news_hash(item: NewsItem) -> str:
    base = f"{item.ticker}|{item.title}|{item.source}|{item.url}|{item.published_at}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _interval_lower_bound(
    last_full_cycle_at: str,
    fallback_hours: int,
    now_utc: datetime,
) -> datetime:
    """Lower bound for accepting news.

    Returns the timestamp of the previous successful cycle. If there is no
    previous cycle (first run / corrupted state), falls back to `now - fallback_hours`.
    """
    if last_full_cycle_at:
        try:
            parsed = datetime.fromisoformat(last_full_cycle_at)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            logger.warning("Invalid last_full_cycle_at=%r; falling back to recent window", last_full_cycle_at)
    return now_utc - timedelta(hours=fallback_hours)


def _published_after(item: NewsItem, lower_bound_utc: datetime) -> bool:
    try:
        published = datetime.fromisoformat(item.published_at)
    except ValueError:
        return False
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return published.astimezone(timezone.utc) > lower_bound_utc


def _process_commands(client: TelegramClient, state: BotState, configured_chat_id: str) -> tuple[BotState, bool]:
    try:
        updates = client.get_updates(offset=state.telegram_offset + 1)
    except Exception:
        logger.exception("Failed to fetch Telegram updates")
        return state, False
    updated_portfolio = False

    for update in updates:
        state.telegram_offset = max(state.telegram_offset, _to_int(update.get("update_id", 0)))
        message = update.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))
        if configured_chat_id and chat_id != configured_chat_id:
            continue
        text = str(message.get("text", "")).strip()
        if not text.lower().startswith("/updatestocks"):
            continue
        tickers = parse_tickers_from_text(text)
        if not tickers:
            try:
                client.send_message(
                    "Usage: /updatestocks RELIANCE, TCS, INFY",
                    chat_id=chat_id,
                )
            except Exception:
                logger.exception("Failed to send usage message to Telegram chat %s", chat_id)
            continue
        _save_portfolio(tickers)
        updated_portfolio = True
        try:
            client.send_message(
                f"Portfolio updated. Tracking: {comma_join(tickers)}",
                chat_id=chat_id,
            )
        except Exception:
            logger.exception("Failed to send portfolio confirmation to Telegram chat %s", chat_id)

    return state, updated_portfolio


def _format_headline(item: NewsItem) -> str:
    source = item.source or "Unknown"
    label = classify_headline(item.title)
    prefix = f"{label} " if label else ""
    return f"- {prefix}{source}: {item.title}"


def run_bot_cycle(config: Config, commands_only: bool = False) -> None:
    _ensure_files()
    now = datetime.now(config.timezone)
    now_utc = now.astimezone(timezone.utc)
    state = _load_state()
    client = TelegramClient(config.telegram_bot_token, config.telegram_chat_id)

    state, _ = _process_commands(client=client, state=state, configured_chat_id=config.telegram_chat_id)
    if commands_only:
        _save_state(state)
        return

    tickers = _portfolio()
    if not tickers:
        logger.info("No portfolio list available yet")
        _save_state(state)
        return

    lower_bound_utc = _interval_lower_bound(
        last_full_cycle_at=state.last_full_cycle_at,
        fallback_hours=config.news_recent_hours,
        now_utc=now_utc,
    )
    logger.info("Accepting news published after %s UTC", lower_bound_utc.isoformat())

    fundamentals = []
    for ticker in tickers:
        try:
            fundamentals.append(fetch_fundamentals(ticker))
        except Exception:
            logger.exception("Failed fetching fundamentals for %s", ticker)

    all_news: list[NewsItem] = []
    for ticker in tickers:
        try:
            # Pull a wide net then filter by interval lower bound below.
            all_news.extend(
                fetch_stock_news(
                    ticker=ticker,
                    max_items=config.max_news_per_stock,
                    recent_hours=max(config.news_recent_hours, 24),
                )
            )
        except Exception:
            logger.exception("Failed fetching news for %s", ticker)

    sent_hashes_set = set(state.sent_hashes)
    by_ticker: dict[str, list[NewsItem]] = {ticker: [] for ticker in tickers}
    # Per-ticker title fingerprints for within-cycle near-duplicate detection.
    # Kept per-ticker to avoid false positives between different companies.
    ticker_fingerprints: dict[str, list[frozenset[str]]] = {t: [] for t in tickers}
    for item in all_news:
        if not _published_after(item, lower_bound_utc):
            continue
        # Exact dedup — same article URL/title/source seen in any prior cycle.
        digest = _news_hash(item)
        if digest in sent_hashes_set:
            continue
        # Near-duplicate dedup — same story from a different source this cycle.
        fp = title_fingerprint(item.title)
        ticker_fps = ticker_fingerprints.setdefault(item.ticker, [])
        if is_duplicate_title(fp, ticker_fps):
            logger.info("Skipping near-duplicate headline for %s: %s", item.ticker, item.title[:80])
            sent_hashes_set.add(digest)
            state.sent_hashes.append(digest)
            continue
        ticker_fps.append(fp)
        sent_hashes_set.add(digest)
        state.sent_hashes.append(digest)
        by_ticker.setdefault(item.ticker, []).append(item)

    for stock_data in fundamentals:
        try:
            news_for_ticker = by_ticker.get(stock_data.ticker, [])
            if not news_for_ticker:
                logger.info("Skipping %s: no new headlines this cycle", stock_data.ticker)
                continue

            news_lines = [_format_headline(n) for n in news_for_ticker[:config.max_news_per_stock]]
            payload = (
                f"{render_fundamentals_table(stock_data)}\n\n"
                f"News\n" + "\n".join(news_lines)
            )
            client.send_message(payload)

            charts = create_price_charts(stock_data.ticker, CHART_DIR)
            for label, chart_path in charts:
                client.send_photo(chart_path, caption=f"{stock_data.ticker} price chart ({label})")
        except Exception:
            logger.exception("Failed sending update for %s", stock_data.ticker)

    state.last_full_cycle_at = now_utc.isoformat()
    _save_state(state)
