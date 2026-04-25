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

The app auto-loads values from `.env` using `python-dotenv`.

## GitHub Actions scheduling model

GitHub Actions cannot natively run every minute. This project uses GitHub-only scheduling:

- `.github/workflows/scheduled-run.yml`
  - runs every 5 minutes
  - bot logic sends full updates every 5 minutes during market hours and every 15 minutes during off-hours
- `.github/workflows/telegram-webhook.yml`
  - syncs `/updatestocks` command state every 5 minutes, offset by 2 minutes to reduce overlap

## Notes on request cap

- One Gemini request verifies all fetched news items in each cycle.
- If daily usage approaches cap or during off-hours pressure, the bot can skip verification and still send data/news with a note.

