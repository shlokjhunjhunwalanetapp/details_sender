#!/usr/bin/env bash
# Cloudflare Worker setup script
# Run once after `wrangler deploy` to wire everything up.
#
# Prerequisites:
#   npm install -g wrangler
#   wrangler login

set -euo pipefail

echo "=== Stock News Bot — Cloudflare Worker Setup ==="

# ── 1. Deploy the worker ──────────────────────────────────────────────────────
echo ""
echo "Step 1: Deploying worker..."
wrangler deploy
WORKER_URL=$(wrangler deployments list --json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['url'])" 2>/dev/null || echo "")
if [ -z "$WORKER_URL" ]; then
  echo "  Could not auto-detect worker URL."
  echo "  Go to https://dash.cloudflare.com → Workers → stock-news-bot and copy the URL."
  read -r -p "  Paste your worker URL here: " WORKER_URL
fi
echo "  Worker URL: $WORKER_URL"

# ── 2. Set secrets ────────────────────────────────────────────────────────────
echo ""
echo "Step 2: Setting secrets (you will be prompted for each value)..."

read -r -p "  TELEGRAM_BOT_TOKEN (from @BotFather): " BOT_TOKEN
echo "$BOT_TOKEN" | wrangler secret put TELEGRAM_BOT_TOKEN

read -r -p "  TELEGRAM_CHAT_ID (your chat ID): " CHAT_ID
echo "$CHAT_ID" | wrangler secret put TELEGRAM_CHAT_ID

# Generate a random secret token for webhook verification
SECRET_TOKEN=$(python3 -c "import secrets; print(secrets.token_hex(32))")
echo "$SECRET_TOKEN" | wrangler secret put TELEGRAM_SECRET_TOKEN
echo "  Generated TELEGRAM_SECRET_TOKEN: $SECRET_TOKEN"
echo "  (save this somewhere safe)"

read -r -p "  GITHUB_TOKEN (fine-grained PAT with Contents:write): " GH_TOKEN
echo "$GH_TOKEN" | wrangler secret put GITHUB_TOKEN

# ── 3. Register Telegram webhook ──────────────────────────────────────────────
echo ""
echo "Step 3: Registering Telegram webhook..."
RESPONSE=$(curl -s \
  -F "url=${WORKER_URL}" \
  -F "secret_token=${SECRET_TOKEN}" \
  -F "allowed_updates=[\"message\"]" \
  "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook")
echo "  Telegram response: $RESPONSE"

# ── 4. Verify ─────────────────────────────────────────────────────────────────
echo ""
echo "Step 4: Verifying webhook..."
curl -s "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo" | python3 -c "
import sys, json
d = json.load(sys.stdin)
r = d.get('result', {})
print(f'  URL: {r.get(\"url\", \"not set\")}')
print(f'  Pending updates: {r.get(\"pending_update_count\", 0)}')
print(f'  Last error: {r.get(\"last_error_message\", \"none\")}')
"

echo ""
echo "=== Setup complete! ==="
echo "Send /start to your bot in Telegram — you should get an instant reply."
echo ""
echo "The news cycle (GitHub Actions) continues unchanged every 5 minutes."
