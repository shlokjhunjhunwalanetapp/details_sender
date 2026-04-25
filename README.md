# Telegram Stock News Bot

Telegram bot for Indian portfolio tracking that:
- accepts `/updatestocks` in chat,
- keeps the latest portfolio list for future cycles,
- fetches latest stock news + fundamentals,
- verifies all cycle news in one Gemini request,
- sends a tabular fundamentals report and a chart image.

## How it works

1. `python -m src.main --commands-only` reads Telegram updates and stores the latest `/updatestocks` list in `data/portfolio.json`.
2. `python -m src.main` uses that saved list, fetches fundamentals/news, verifies news in one Gemini call, then sends results to Telegram.
3. `data/request_budget.json` tracks daily LLM usage, Telegram update offset, and recent sent news hashes.

## Required secrets and vars

Add these in your GitHub repository:

- `TELEGRAM_BOT_TOKEN` (secret)
- `TELEGRAM_CHAT_ID` (secret)
- `GEMINI_API_KEY` (secret)
- `GEMINI_MODEL` (variable, optional; default `gemini-1.5-flash`)
- `LLM_DAILY_CAP` (variable, optional; default `1500`)

## Local run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m src.main --commands-only
python -m src.main
```

## GitHub Actions scheduling model

GitHub Actions cannot natively run every minute. This project supports:

- `.github/workflows/scheduled-run.yml`
  - `repository_dispatch` type `market_tick` (for external 1-minute trigger during market hours)
  - `repository_dispatch` type `offhour_tick` (for external 15-minute trigger off-hours)
  - built-in fallback `schedule` every 15 minutes
- `.github/workflows/telegram-webhook.yml`
  - syncs `/updatestocks` command state every 5 minutes and on dispatch

## External 1-minute trigger (free)

Use a free external cron provider that can send an HTTP POST to:

- `https://api.github.com/repos/<owner>/<repo>/dispatches`

Body:

```json
{"event_type":"market_tick"}
```

Headers:
- `Authorization: Bearer <github_pat_with_repo_scope>`
- `Accept: application/vnd.github+json`

Create another cron for off-hours with:

```json
{"event_type":"offhour_tick"}
```

## Notes on request cap

- One Gemini request verifies all fetched news items in each cycle.
- If daily usage approaches cap or during off-hours pressure, the bot can skip verification and still send data/news with a note.

