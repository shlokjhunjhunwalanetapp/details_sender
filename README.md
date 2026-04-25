# Telegram Stock News Bot

Telegram bot for Indian portfolio tracking that:
- accepts `/updatestocks` in chat to set your watchlist,
- every cycle, fetches news published **since the previous run** so you only see new headlines,
- sends a tabular fundamentals report + 3-month, 1-year, and all-time price charts,
- runs entirely on GitHub Actions — no external services required.

## How it works

1. `python -m src.main --commands-only` reads Telegram updates and saves the latest `/updatestocks` list in `data/portfolio.json`.
2. `python -m src.main` loads that list, fetches news and fundamentals, filters to headlines newer than the previous cycle, and sends results to Telegram.
3. `data/request_budget.json` persists the Telegram offset, sent-news hashes, and the timestamp of the last successful cycle.

## Required secrets

Add these in your GitHub repository (Settings → Secrets and variables → Actions):

| Name | Type | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Secret | Your bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Secret | Your personal or group chat ID |

No API keys are needed beyond Telegram.

## Optional variables

| Name | Default | Description |
|---|---|---|
| `MAX_NEWS_PER_STOCK` | `6` | Max headlines shown per stock |
| `NEWS_RECENT_HOURS` | `24` | Fallback window on first run |
| `MARKET_OPEN` | `09:15` | IST market open time |
| `MARKET_CLOSE` | `15:30` | IST market close time |

## Local run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env
python -m src.main --commands-only   # pick up /updatestocks from Telegram
python -m src.main                   # send stock updates
```

## GitHub Actions scheduling

- `.github/workflows/scheduled-run.yml` — runs every 5 minutes, sends full updates.
- `.github/workflows/telegram-webhook.yml` — runs every 5 minutes (offset by 2 min) to pick up `/updatestocks` commands.

Both workflows persist state back to the repo so the next run knows which cycle it is and only sends truly new headlines.
