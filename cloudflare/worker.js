/**
 * Telegram Webhook Handler — Cloudflare Worker
 *
 * Handles bot commands instantly (< 1s) without polling.
 * News updates continue to run on GitHub Actions every 5 minutes.
 *
 * Environment variables (set via `wrangler secret put`):
 *   TELEGRAM_BOT_TOKEN      — from @BotFather
 *   TELEGRAM_CHAT_ID        — your personal/group chat ID
 *   TELEGRAM_SECRET_TOKEN   — random string you generate (used to verify Telegram)
 *   GITHUB_TOKEN            — fine-grained PAT with Contents:write on this repo
 *   GITHUB_REPO             — e.g. "username/all_stock_details_sender"
 */

// ── Ticker → company name registry ───────────────────────────────────────────
// Loaded at runtime from data/ticker_names.json in the GitHub repo.
// Falls back to the hardcoded map below if the fetch fails.
let _registry = null;

async function getRegistry(env) {
  if (_registry) return _registry;
  try {
    const resp = await fetch(
      `https://raw.githubusercontent.com/${env.GITHUB_REPO}/main/data/ticker_names.json`,
      { headers: { "User-Agent": "StockNewsBot/1.0" } },
    );
    if (resp.ok) {
      const data = await resp.json();
      _registry = data.tickers || {};
      return _registry;
    }
  } catch {}
  _registry = TICKER_FALLBACK;
  return _registry;
}

async function lookupCompany(ticker, env) {
  const registry = await getRegistry(env);
  return registry[ticker.toUpperCase()] || ticker;
}

// Fallback hardcoded map (used only if GitHub fetch fails)
const TICKER_FALLBACK = {
  RELIANCE: "Reliance Industries",
  TCS: "Tata Consultancy Services",
  INFY: "Infosys",
  HDFCBANK: "HDFC Bank",
  ICICIBANK: "ICICI Bank",
  HINDUNILVR: "Hindustan Unilever",
  SBIN: "State Bank of India",
  BAJFINANCE: "Bajaj Finance",
  BHARTIARTL: "Bharti Airtel",
  KOTAKBANK: "Kotak Mahindra Bank",
  LT: "Larsen Toubro",
  AXISBANK: "Axis Bank",
  ASIANPAINT: "Asian Paints",
  MARUTI: "Maruti Suzuki",
  SUNPHARMA: "Sun Pharmaceutical",
  TITAN: "Titan Company",
  WIPRO: "Wipro",
  TECHM: "Tech Mahindra",
  HCLTECH: "HCL Technologies",
  ULTRACEMCO: "UltraTech Cement",
  NESTLEIND: "Nestle India",
  ADANIENT: "Adani Enterprises",
  ADANIPORTS: "Adani Ports",
  POWERGRID: "Power Grid Corporation",
  NTPC: "NTPC",
  ONGC: "ONGC",
  COALINDIA: "Coal India",
  BPCL: "BPCL",
  DIVISLAB: "Divi's Laboratories",
  DRREDDY: "Dr Reddy's Laboratories",
  CIPLA: "Cipla",
  GRASIM: "Grasim Industries",
  EICHERMOT: "Eicher Motors",
  "BAJAJ-AUTO": "Bajaj Auto",
  HEROMOTOCO: "Hero MotoCorp",
  "M&M": "Mahindra Mahindra",
  TATACONSUM: "Tata Consumer Products",
  BRITANNIA: "Britannia Industries",
  HINDALCO: "Hindalco Industries",
  TATASTEEL: "Tata Steel",
  JSWSTEEL: "JSW Steel",
  INDUSINDBK: "IndusInd Bank",
  SBILIFE: "SBI Life Insurance",
  HDFCLIFE: "HDFC Life Insurance",
  ICICIGI: "ICICI Lombard",
  ITC: "ITC",
  PIDILITIND: "Pidilite Industries",
  HAVELLS: "Havells India",
  SIEMENS: "Siemens India",
  ABB: "ABB India",
  IRCTC: "IRCTC",
  DMART: "Avenue Supermarts DMart",
  ZOMATO: "Zomato",
  NYKAA: "Nykaa FSN E-Commerce",
  PAYTM: "Paytm One97 Communications",
  POLICYBZR: "PB Fintech PolicyBazaar",
  MAPMYINDIA: "MapMyIndia CE Info Systems",
  // Defence / PSU
  HAL: "Hindustan Aeronautics",
  BEL: "Bharat Electronics",
  BHEL: "Bharat Heavy Electricals",
  SAIL: "Steel Authority of India",
  NMDC: "NMDC",
  GAIL: "GAIL India",
  IOC: "Indian Oil Corporation",
  HPCL: "Hindustan Petroleum Corporation",
  RECLTD: "REC Limited",
  PFC: "Power Finance Corporation",
  IRFC: "Indian Railway Finance Corporation",
  CONCOR: "Container Corporation of India",
  NBCC: "NBCC India",
  NHPC: "NHPC",
  SJVN: "SJVN",
  COCHINSHIP: "Cochin Shipyard",
  MAZAGON: "Mazagon Dock Shipbuilders",
  GRSE: "Garden Reach Shipbuilders",
  BDL: "Bharat Dynamics",
  BEML: "BEML",
  TATAMOTORS: "Tata Motors",
  ZOMATO: "Zomato",
  NYKAA: "Nykaa",
  DELHIVERY: "Delhivery",
};

const HELP_TEXT = `Stock News Bot — Commands

/start          Show this welcome message
/help           Show all commands
/list           Show your current watchlist
/addstock TICKER      Add one stock (e.g. /addstock ZOMATO)
/removestock TICKER   Remove one stock (e.g. /removestock TCS)
/updatestocks TICKER1, TICKER2, ...
                Replace the entire watchlist at once

Use NSE ticker symbols (e.g. RELIANCE, HDFCBANK, INFY).
The bot checks for news every 5 minutes and sends updates
only when new headlines are found for a stock.`;


// ── Telegram helpers ──────────────────────────────────────────────────────────
async function sendMessage(chatId, text, env) {
  await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, text, disable_web_page_preview: true }),
  });
}


// ── GitHub portfolio read / write ─────────────────────────────────────────────
async function getPortfolio(env) {
  try {
    const resp = await fetch(
      `https://raw.githubusercontent.com/${env.GITHUB_REPO}/main/data/portfolio.json`,
      { headers: { "User-Agent": "StockNewsBot/1.0" } },
    );
    if (!resp.ok) return [];
    const data = await resp.json();
    return data.tickers || [];
  } catch {
    return [];
  }
}

async function savePortfolio(tickers, env) {
  const content =
    JSON.stringify({ tickers, updated_at: new Date().toISOString() }, null, 2) + "\n";
  // btoa with UTF-8 support
  const encoded = btoa(
    Array.from(new TextEncoder().encode(content), (b) => String.fromCharCode(b)).join(""),
  );

  // Fetch current SHA (required for updating an existing file)
  const getResp = await fetch(
    `https://api.github.com/repos/${env.GITHUB_REPO}/contents/data/portfolio.json`,
    {
      headers: {
        Authorization: `token ${env.GITHUB_TOKEN}`,
        "User-Agent": "StockNewsBot/1.0",
        Accept: "application/vnd.github.v3+json",
      },
    },
  );

  const putBody = {
    message: "chore: update portfolio via bot command",
    content: encoded,
    committer: {
      name: "Stock Bot",
      email: "stockbot@users.noreply.github.com",
    },
  };
  if (getResp.ok) {
    const fileData = await getResp.json();
    if (fileData.sha) putBody.sha = fileData.sha;
  }

  await fetch(
    `https://api.github.com/repos/${env.GITHUB_REPO}/contents/data/portfolio.json`,
    {
      method: "PUT",
      headers: {
        Authorization: `token ${env.GITHUB_TOKEN}`,
        "Content-Type": "application/json",
        "User-Agent": "StockNewsBot/1.0",
        Accept: "application/vnd.github.v3+json",
      },
      body: JSON.stringify(putBody),
    },
  );
}


// ── Ticker parsing helpers ────────────────────────────────────────────────────
function normalizeTicker(t) {
  return t.trim().toUpperCase().replace(/[^A-Z0-9.\-&]/g, "");
}

function parseTickersFromText(text, command) {
  const body = text.replace(new RegExp(`^\\/${command}(@\\w+)?`, "i"), "").trim();
  const unique = [];
  const seen = new Set();
  for (const part of body.split(/[\s,;]+/)) {
    const t = normalizeTicker(part);
    if (t && !seen.has(t)) {
      seen.add(t);
      unique.push(t);
    }
  }
  return unique;
}

function parseSingleTicker(text, command) {
  return parseTickersFromText(text, command)[0] ?? null;
}

async function formatPortfolio(tickers, env) {
  if (!tickers.length) {
    return (
      "Your watchlist is empty.\n" +
      "Add stocks with /addstock TICKER\n" +
      "or set a full list with /updatestocks TICKER1, TICKER2, ..."
    );
  }
  const lines = ["Currently tracking:\n"];
  for (let i = 0; i < tickers.length; i++) {
    const t = tickers[i];
    const company = await lookupCompany(t, env);
    lines.push(`  ${i + 1}. ${company !== t ? `${company} (${t})` : t}`);
  }
  lines.push(`\n${tickers.length} stock(s) total.`);
  lines.push("Use /addstock or /removestock to change the list.");
  return lines.join("\n");
}


// ── Command dispatcher ────────────────────────────────────────────────────────
async function handleCommand(text, chatId, env) {
  const cmd = text.split(/[\s@]/)[0].slice(1).toLowerCase();

  if (cmd === "start" || cmd === "help") {
    await sendMessage(chatId, HELP_TEXT, env);
    return;
  }

  if (cmd === "list") {
    const tickers = await getPortfolio(env);
    await sendMessage(chatId, await formatPortfolio(tickers, env), env);
    return;
  }

  if (cmd === "addstock") {
    const ticker = parseSingleTicker(text, "addstock");
    if (!ticker) {
      await sendMessage(chatId, "Please give a ticker symbol.\nExample: /addstock ZOMATO", env);
      return;
    }
    const tickers = await getPortfolio(env);
    if (tickers.includes(ticker)) {
      await sendMessage(
        chatId,
        `${ticker} is already in your watchlist.\n\n${await formatPortfolio(tickers, env)}`,
        env,
      );
      return;
    }
    tickers.push(ticker);
    await savePortfolio(tickers, env);
    await sendMessage(chatId, `Added ${ticker}.\n\n${await formatPortfolio(tickers, env)}`, env);
    return;
  }

  if (cmd === "removestock") {
    const ticker = parseSingleTicker(text, "removestock");
    if (!ticker) {
      await sendMessage(chatId, "Please give a ticker symbol.\nExample: /removestock TCS", env);
      return;
    }
    const tickers = await getPortfolio(env);
    const idx = tickers.indexOf(ticker);
    if (idx === -1) {
      await sendMessage(
        chatId,
        `${ticker} is not in your watchlist.\n\n${await formatPortfolio(tickers, env)}`,
        env,
      );
      return;
    }
    tickers.splice(idx, 1);
    await savePortfolio(tickers, env);
    await sendMessage(chatId, `Removed ${ticker}.\n\n${await formatPortfolio(tickers, env)}`, env);
    return;
  }

  if (cmd === "updatestocks") {
    const tickers = parseTickersFromText(text, "updatestocks");
    if (!tickers.length) {
      await sendMessage(
        chatId,
        "Please list at least one ticker.\nExample: /updatestocks RELIANCE, TCS, INFY",
        env,
      );
      return;
    }
    await savePortfolio(tickers, env);
    await sendMessage(chatId, `Watchlist replaced.\n\n${await formatPortfolio(tickers, env)}`, env);
    return;
  }
}


// ── Worker entry point ────────────────────────────────────────────────────────
export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("Stock News Bot — webhook endpoint is live.", { status: 200 });
    }

    // Verify the request came from Telegram using the secret token we set.
    const secretToken = request.headers.get("X-Telegram-Bot-Api-Secret-Token");
    if (env.TELEGRAM_SECRET_TOKEN && secretToken !== env.TELEGRAM_SECRET_TOKEN) {
      return new Response("Unauthorized", { status: 401 });
    }

    try {
      const body = await request.json();
      const message = body.message;
      if (!message?.text) return new Response("OK");

      const chatId = String(message.chat.id);
      const text = message.text.trim();

      // Ignore messages from other chats.
      if (env.TELEGRAM_CHAT_ID && chatId !== env.TELEGRAM_CHAT_ID) {
        return new Response("OK");
      }

      if (text.startsWith("/")) {
        // Handle command in the background so Telegram doesn't time out.
        env.ctx?.waitUntil(handleCommand(text, chatId, env));
        // If no execution context (local dev), await directly.
        if (!env.ctx) await handleCommand(text, chatId, env);
      }
    } catch (err) {
      console.error("Worker error:", err);
    }

    return new Response("OK");
  },
};
