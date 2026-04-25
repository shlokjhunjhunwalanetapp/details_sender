from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from src.charting import create_price_chart
from src.config import Config
from src.formatter import render_fundamentals_table
from src.fundamentals_fetcher import fetch_fundamentals
from src.news_fetcher import NewsItem, fetch_stock_news
from src.portfolio_parser import comma_join, parse_tickers_from_text
from src.verifier import VerifiedNews, verify_news_batch


logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
PORTFOLIO_PATH = DATA_DIR / "portfolio.json"
REQUEST_BUDGET_PATH = DATA_DIR / "request_budget.json"
CHART_DIR = Path("tmp/charts")


@dataclass
class BudgetState:
    date: str
    llm_requests_used: int
    telegram_offset: int
    sent_hashes: list[str]
    last_full_cycle_at: str


class TelegramClient:
    def __init__(self, token: str, chat_id: str = "") -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.chat_id = chat_id

    def get_updates(self, offset: int) -> list[dict[str, Any]]:
        response = requests.get(
            f"{self.base_url}/getUpdates",
            params={"offset": offset, "timeout": 0},
            timeout=25,
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("result", [])

    def send_message(self, text: str, chat_id: str | None = None) -> None:
        target = chat_id or self.chat_id
        if not target:
            return
        response = requests.post(
            f"{self.base_url}/sendMessage",
            json={"chat_id": target, "text": text, "disable_web_page_preview": True},
            timeout=25,
        )
        response.raise_for_status()

    def send_photo(self, photo_path: Path, caption: str = "", chat_id: str | None = None) -> None:
        target = chat_id or self.chat_id
        if not target:
            return
        with photo_path.open("rb") as f:
            response = requests.post(
                f"{self.base_url}/sendPhoto",
                data={"chat_id": target, "caption": caption},
                files={"photo": f},
                timeout=45,
            )
        response.raise_for_status()


def _ensure_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not PORTFOLIO_PATH.exists():
        PORTFOLIO_PATH.write_text(json.dumps({"tickers": [], "updated_at": ""}, indent=2), encoding="utf-8")
    if not REQUEST_BUDGET_PATH.exists():
        REQUEST_BUDGET_PATH.write_text(
            json.dumps(
                {
                    "date": "",
                    "llm_requests_used": 0,
                    "telegram_offset": 0,
                    "sent_hashes": [],
                },
                indent=2,
            ),
            encoding="utf-8",
        )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _load_budget(today: str) -> BudgetState:
    raw = _read_json(REQUEST_BUDGET_PATH)
    if raw.get("date") != today:
        return BudgetState(
            date=today,
            llm_requests_used=0,
            telegram_offset=int(raw.get("telegram_offset", 0)),
            sent_hashes=[],
            last_full_cycle_at=str(raw.get("last_full_cycle_at", "")),
        )
    return BudgetState(
        date=today,
        llm_requests_used=int(raw.get("llm_requests_used", 0)),
        telegram_offset=int(raw.get("telegram_offset", 0)),
        sent_hashes=list(raw.get("sent_hashes", [])),
        last_full_cycle_at=str(raw.get("last_full_cycle_at", "")),
    )


def _save_budget(state: BudgetState) -> None:
    _write_json(
        REQUEST_BUDGET_PATH,
        {
            "date": state.date,
            "llm_requests_used": state.llm_requests_used,
            "telegram_offset": state.telegram_offset,
            "sent_hashes": state.sent_hashes[-500:],
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


def _should_run_full_cycle(config: Config, now: datetime) -> bool:
    if _is_market_hours(config, now):
        return True
    return False


def _should_run_offhours_cycle(now: datetime, last_full_cycle_at: str) -> bool:
    if not last_full_cycle_at:
        return True
    try:
        last_run = datetime.fromisoformat(last_full_cycle_at)
    except ValueError:
        return True
    if last_run.tzinfo is None:
        last_run = last_run.replace(tzinfo=now.tzinfo)
    # GitHub schedule can drift by a few minutes, so gate by elapsed time.
    return (now - last_run) >= timedelta(minutes=15)


def _news_hash(item: NewsItem) -> str:
    base = f"{item.ticker}|{item.title}|{item.source}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _process_commands(client: TelegramClient, budget: BudgetState, configured_chat_id: str) -> tuple[BudgetState, bool]:
    updates = client.get_updates(offset=budget.telegram_offset + 1)
    updated_portfolio = False

    for update in updates:
        budget.telegram_offset = max(budget.telegram_offset, int(update.get("update_id", 0)))
        message = update.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))
        if configured_chat_id and chat_id != configured_chat_id:
            continue
        text = str(message.get("text", "")).strip()
        if not text.lower().startswith("/updatestocks"):
            continue
        tickers = parse_tickers_from_text(text)
        if not tickers:
            client.send_message(
                "Usage: /updatestocks RELIANCE, TCS, INFY",
                chat_id=chat_id,
            )
            continue
        _save_portfolio(tickers)
        updated_portfolio = True
        client.send_message(
            f"Portfolio updated. Tracking: {comma_join(tickers)}",
            chat_id=chat_id,
        )

    return budget, updated_portfolio


def _fallback_unverified(items: list[NewsItem], reason: str) -> list[VerifiedNews]:
    return [
        VerifiedNews(
            ticker=item.ticker,
            title=item.title,
            url=item.url,
            source=item.source,
            authenticity_score=50,
            verdict="uncertain",
            confidence="low",
            reason=reason,
        )
        for item in items
    ]


def run_bot_cycle(config: Config, commands_only: bool = False, force_verify: bool = False) -> None:
    _ensure_files()
    now = datetime.now(config.timezone)
    today = now.date().isoformat()
    budget = _load_budget(today=today)
    client = TelegramClient(config.telegram_bot_token, config.telegram_chat_id)

    budget, _ = _process_commands(client=client, budget=budget, configured_chat_id=config.telegram_chat_id)
    if commands_only:
        _save_budget(budget)
        return
    if not force_verify and not _should_run_full_cycle(config, now) and not _should_run_offhours_cycle(now, budget.last_full_cycle_at):
        logger.info("Skipping full cycle this run (off-hours non-15-minute tick)")
        _save_budget(budget)
        return

    tickers = _portfolio()
    if not tickers:
        logger.info("No portfolio list available yet")
        _save_budget(budget)
        return

    fundamentals = [fetch_fundamentals(ticker) for ticker in tickers]
    all_news: list[NewsItem] = []
    for ticker in tickers:
        all_news.extend(fetch_stock_news(ticker=ticker, max_items=config.max_news_per_stock))

    unseen_news: list[NewsItem] = []
    for item in all_news:
        digest = _news_hash(item)
        if digest in budget.sent_hashes:
            continue
        unseen_news.append(item)
        budget.sent_hashes.append(digest)

    should_verify = force_verify or _is_market_hours(config=config, now=now) or budget.llm_requests_used < int(config.llm_daily_cap * 0.8)
    if unseen_news and should_verify and budget.llm_requests_used < config.llm_daily_cap and config.gemini_api_key:
        try:
            verified_news = verify_news_batch(
                api_key=config.gemini_api_key,
                model=config.gemini_model,
                items=unseen_news,
            )
            budget.llm_requests_used += 1
        except Exception:
            logger.exception("Verification failed, using fallback")
            verified_news = _fallback_unverified(unseen_news, "Gemini verification failed in this cycle")
    else:
        reason = "Verification skipped due to budget/off-hours policy"
        verified_news = _fallback_unverified(unseen_news, reason)

    by_ticker: dict[str, list[VerifiedNews]] = {ticker: [] for ticker in tickers}
    for item in verified_news:
        by_ticker.setdefault(item.ticker, []).append(item)

    for stock_data in fundamentals:
        news_for_ticker = by_ticker.get(stock_data.ticker, [])
        news_lines = [f"- {n.verdict}:{n.authenticity_score} {n.title}" for n in news_for_ticker[:3]]
        if not news_lines:
            news_lines = ["- No new headlines in this cycle"]

        payload = (
            f"{render_fundamentals_table(stock_data)}\n\n"
            f"News\n" + "\n".join(news_lines) + "\n\n"
            f"LLM usage today: {budget.llm_requests_used}/{config.llm_daily_cap}"
        )
        client.send_message(payload)

        chart_path = create_price_chart(stock_data.ticker, CHART_DIR)
        if chart_path:
            client.send_photo(chart_path, caption=f"{stock_data.ticker} price chart (3M)")

    budget.last_full_cycle_at = now.isoformat()
    _save_budget(budget)
