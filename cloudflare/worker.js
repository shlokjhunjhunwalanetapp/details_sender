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
  // Ticker names don't change frequently — raw URL (with caching) is fine here.
  try {
    const resp = await fetch(
      `https://raw.githubusercontent.com/${env.GITHUB_REPO}/main/data/ticker_names.json`,
      { headers: { "User-Agent": "StockNewsBot/1.0" }, cf: { cacheTtl: 3600 } },
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

async function sendMessageWithKeyboard(chatId, text, keyboard, env) {
  await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chat_id: chatId,
      text,
      disable_web_page_preview: true,
      reply_markup: keyboard,
    }),
  });
}

async function answerCallbackQuery(callbackQueryId, text, env) {
  await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/answerCallbackQuery`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ callback_query_id: callbackQueryId, text }),
  });
}


// ── GitHub portfolio read / write ─────────────────────────────────────────────
async function getPortfolio(env) {
  // Use the GitHub Contents API — NOT the raw CDN URL.
  // raw.githubusercontent.com is cached for up to 5 minutes, which causes
  // stale reads when commands fire within seconds of each other, silently
  // dropping stocks that were just added.
  try {
    const resp = await fetch(
      `https://api.github.com/repos/${env.GITHUB_REPO}/contents/data/portfolio.json`,
      {
        headers: {
          Authorization: `token ${env.GITHUB_TOKEN}`,
          Accept: "application/vnd.github.v3+json",
          "User-Agent": "StockNewsBot/1.0",
        },
      },
    );
    if (!resp.ok) return [];
    const file = await resp.json();
    // Content is base64-encoded by the GitHub API.
    const decoded = atob(file.content.replace(/\n/g, ""));
    const data = JSON.parse(decoded);
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


// ── Ticker validation ─────────────────────────────────────────────────────────
async function validateAndSuggest(ticker, env) {
  const registry = await getRegistry(env);

  // Exact match — fully valid NSE ticker.
  if (registry[ticker]) {
    return { valid: true, name: registry[ticker], suggestions: [] };
  }

  // Not found — find close matches to suggest.
  const suggestions = [];
  const t = ticker.toUpperCase();

  // 1. Symbol starts with the query (prefix match).
  for (const [sym, name] of Object.entries(registry)) {
    if (sym.startsWith(t) && sym !== t) {
      suggestions.push({ sym, name });
      if (suggestions.length >= 3) break;
    }
  }

  // 2. Company name contains the query.
  if (suggestions.length < 3) {
    for (const [sym, name] of Object.entries(registry)) {
      if (name.toUpperCase().includes(t) && !suggestions.find(s => s.sym === sym)) {
        suggestions.push({ sym, name });
        if (suggestions.length >= 3) break;
      }
    }
  }

  return { valid: false, name: null, suggestions };
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
      // Show search button (one at a time) AND a hint for bulk add.
      await sendMessageWithKeyboard(
        chatId,
        "How would you like to add stocks?\n\n• Tap 🔍 to search and add one stock\n• Use /updatestocks RELIANCE, TCS, HAL to add multiple at once",
        {
          inline_keyboard: [
            [{ text: "🔍 Search & add a stock", switch_inline_query_current_chat: "" }],
          ],
        },
        env,
      );
      return;
    }
    // Validate ticker against NSE registry before adding.
    const check = await validateAndSuggest(ticker, env);
    if (!check.valid) {
      let msg = `⚠️ "${ticker}" is not a recognised NSE ticker and may produce no results.\n`;
      if (check.suggestions.length) {
        msg += "\nDid you mean:\n";
        msg += check.suggestions.map(s => `  • ${s.sym} — ${s.name}`).join("\n");
        msg += "\n\nOr use 🔍 to search by company name.";
      } else {
        msg += "\nUse 🔍 to search by company name instead.";
      }
      const keyboard = { inline_keyboard: [] };
      // Add quick-tap buttons for suggestions.
      if (check.suggestions.length) {
        keyboard.inline_keyboard.push(
          check.suggestions.map(s => ({ text: `${s.sym}`, callback_data: `/addstock ${s.sym}` }))
        );
      }
      keyboard.inline_keyboard.push([{ text: "🔍 Search by name", switch_inline_query_current_chat: "" }]);
      await sendMessageWithKeyboard(chatId, msg, keyboard, env);
      return;
    }

    const tickers = await getPortfolio(env);
    if (tickers.includes(ticker)) {
      await sendMessageWithKeyboard(
        chatId,
        `${ticker} (${check.name}) is already in your watchlist.\n\n${await formatPortfolio(tickers, env)}`,
        { inline_keyboard: [[{ text: "🔍 Add another stock", switch_inline_query_current_chat: "" }]] },
        env,
      );
      return;
    }
    tickers.push(ticker);
    await savePortfolio(tickers, env);
    await sendMessageWithKeyboard(
      chatId,
      `✅ Added ${check.name} (${ticker}).\n\n${await formatPortfolio(tickers, env)}`,
      { inline_keyboard: [[{ text: "🔍 Add another stock", switch_inline_query_current_chat: "" }]] },
      env,
    );
    return;
  }

  if (cmd === "removestock") {
    const ticker = parseSingleTicker(text, "removestock");
    if (!ticker) {
      // Show current watchlist as tappable buttons for one-tap removal.
      const tickers = await getPortfolio(env);
      if (!tickers.length) {
        await sendMessage(chatId, "Your watchlist is empty. Nothing to remove.", env);
        return;
      }
      const registry = await getRegistry(env);
      const rows = [];
      for (let i = 0; i < tickers.length; i += 2) {
        const row = [];
        for (const t of tickers.slice(i, i + 2)) {
          const name = registry[t] || t;
          const label = name !== t ? `❌ ${t} (${name})` : `❌ ${t}`;
          row.push({ text: label, callback_data: `/removestock ${t}` });
        }
        rows.push(row);
      }
      await sendMessageWithKeyboard(
        chatId,
        "Tap a stock to remove it from your watchlist:",
        { inline_keyboard: rows },
        env,
      );
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
      // Start visual builder — clear any stale pending state first.
      await env.PENDING_WATCHLIST.put(chatId, JSON.stringify([]), { expirationTtl: 600 });
      const current = await getPortfolio(env);
      const currentStr = current.length ? current.join(", ") : "(empty)";
      await sendMessageWithKeyboard(
        chatId,
        `Build your new watchlist by searching stocks one at a time, then tap ✅ to save.\n\nCurrent watchlist: ${currentStr}\nNew list so far: (none yet)`,
        {
          inline_keyboard: [
            [{ text: "🔍 Search & pick a stock", switch_inline_query_current_chat: ">" }],
            [{ text: "✅ Save new watchlist (0 selected)", callback_data: "confirm_update" }],
          ],
        },
        env,
      );
      return;
    }
    // Called with symbols directly (e.g. /updatestocks RELIANCE, TCS, HAL)
    await savePortfolio(tickers, env);
    await env.PENDING_WATCHLIST.delete(chatId);
    await sendMessage(chatId, `Watchlist replaced.\n\n${await formatPortfolio(tickers, env)}`, env);
    return;
  }

  // /pendingadd SYMBOL — adds one stock to the in-progress builder list
  if (cmd === "pendingadd") {
    const ticker = parseSingleTicker(text, "pendingadd");
    if (!ticker) return;
    const check = await validateAndSuggest(ticker, env);
    if (!check.valid) {
      let msg = `⚠️ "${ticker}" is not a recognised NSE ticker.\n`;
      if (check.suggestions.length) {
        msg += "\nDid you mean:\n" + check.suggestions.map(s => `  • ${s.sym} — ${s.name}`).join("\n");
      }
      const keyboard = { inline_keyboard: [] };
      if (check.suggestions.length) {
        keyboard.inline_keyboard.push(
          check.suggestions.map(s => ({ text: s.sym, callback_data: `/pendingadd ${s.sym}` }))
        );
      }
      keyboard.inline_keyboard.push([{ text: "🔍 Search again", switch_inline_query_current_chat: ">" }]);
      await sendMessageWithKeyboard(chatId, msg, keyboard, env);
      return;
    }
    const raw = await env.PENDING_WATCHLIST.get(chatId);
    const pending = raw ? JSON.parse(raw) : [];
    if (!pending.includes(ticker)) pending.push(ticker);
    await env.PENDING_WATCHLIST.put(chatId, JSON.stringify(pending), { expirationTtl: 600 });
    const registry = await getRegistry(env);
    const lines = pending.map((t, i) => {
      const name = registry[t] || t;
      return `  ${i + 1}. ${name !== t ? `${name} (${t})` : t}`;
    });
    await sendMessageWithKeyboard(
      chatId,
      `Building new watchlist (${pending.length} stock${pending.length !== 1 ? "s" : ""}):\n${lines.join("\n")}\n\nTap 🔍 to add more or ✅ to save.`,
      {
        inline_keyboard: [
          [{ text: "🔍 Add another stock", switch_inline_query_current_chat: ">" }],
          [{ text: `✅ Save new watchlist (${pending.length} selected)`, callback_data: "confirm_update" }],
          [{ text: "❌ Cancel", callback_data: "cancel_update" }],
        ],
      },
      env,
    );
    return;
  }
}


// ── Callback query handler (inline keyboard button taps) ──────────────────────
async function handleCallbackQuery(callbackQuery, env) {
  const chatId = String(callbackQuery.message.chat.id);
  const data = callbackQuery.data || "";

  // Acknowledge the tap immediately so the button stops spinning.
  await answerCallbackQuery(callbackQuery.id, "", env);

  if (data === "confirm_update") {
    const raw = await env.PENDING_WATCHLIST.get(chatId);
    const pending = raw ? JSON.parse(raw) : [];
    if (!pending.length) {
      await sendMessage(chatId, "No stocks selected yet. Use 🔍 to search and pick stocks first.", env);
      return;
    }
    await savePortfolio(pending, env);
    await env.PENDING_WATCHLIST.delete(chatId);
    await sendMessage(chatId, `Watchlist saved!\n\n${await formatPortfolio(pending, env)}`, env);
    return;
  }

  if (data === "cancel_update") {
    await env.PENDING_WATCHLIST.delete(chatId);
    await sendMessage(chatId, "Cancelled. Your previous watchlist is unchanged.", env);
    return;
  }

  // Generic: route /command callback_data to the command handler.
  if (data.startsWith("/")) {
    await handleCommand(data, chatId, env);
  }
}


// ── Command menu (shown when user types "/") ──────────────────────────────────
const BOT_COMMANDS = [
  { command: "start",        description: "Welcome message and all commands" },
  { command: "help",         description: "Show all commands" },
  { command: "list",         description: "Show your current watchlist" },
  { command: "addstock",     description: "Add a stock  — e.g. /addstock RELIANCE" },
  { command: "removestock",  description: "Remove a stock — e.g. /removestock TCS" },
  { command: "updatestocks", description: "Replace entire watchlist — e.g. /updatestocks RELIANCE, TCS" },
];

async function registerCommands(env) {
  await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/setMyCommands`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ commands: BOT_COMMANDS }),
  });
}


// ── Inline mode — stock name autocomplete ─────────────────────────────────────
// Enable in BotFather: /setinline → @yourbot → set placeholder text.
// User types: @yourbot RELI   → sees matching stocks → taps to send /addstock
async function handleInlineQuery(query, env) {
  const raw = query.query.trim();
  // Builder mode: query starts with ">" — results send /pendingadd instead of /addstock
  const builderMode = raw.startsWith(">");
  const q = (builderMode ? raw.slice(1) : raw).trim().toUpperCase();
  const registry = await getRegistry(env);

  let matches = [];
  if (q.length === 0 && !builderMode) {
    // No query, normal mode — show current watchlist for quick removal.
    const tickers = await getPortfolio(env);
    matches = tickers.slice(0, 10).map((sym, i) => {
      const name = registry[sym] || sym;
      return makeInlineResult(i, sym, name, "Already in watchlist — tap to remove", `/removestock ${sym}`);
    });
  } else if (q.length === 0 && builderMode) {
    // Builder mode, no search text yet — show a prompt
    matches = [{
      type: "article", id: "hint", title: "Type a stock name or symbol to search…",
      description: "e.g. RELIANCE, Tata, HDFC",
      input_message_content: { message_text: "/updatestocks" },
    }];
  } else {
    // Search: symbol prefix match first, then company name substring match.
    const prefixMatches = [];
    const nameMatches = [];
    for (const [sym, name] of Object.entries(registry)) {
      if (sym.startsWith(q)) {
        prefixMatches.push([sym, name]);
      } else if (name.toUpperCase().includes(q)) {
        nameMatches.push([sym, name]);
      }
      if (prefixMatches.length + nameMatches.length >= 50) break;
    }
    const combined = [...prefixMatches, ...nameMatches].slice(0, 50);
    const action = builderMode ? "Tap to add to new watchlist" : "Tap to add to watchlist";
    const command = builderMode ? (sym) => `/pendingadd ${sym}` : (sym) => `/addstock ${sym}`;
    matches = combined.map(([sym, name], i) =>
      makeInlineResult(i, sym, name, action, command(sym))
    );
  }

  await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/answerInlineQuery`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      inline_query_id: query.id,
      results: matches,
      cache_time: 10,
      is_personal: true,
    }),
  });
}

function makeInlineResult(index, sym, name, description, messageText) {
  return {
    type: "article",
    id: `${index}_${sym}`,
    title: `${sym}  —  ${name}`,
    description,
    input_message_content: { message_text: messageText },
    thumb_url: "https://upload.wikimedia.org/wikipedia/commons/thumb/5/52/BSE_on_Dalal_Street.JPG/120px-BSE_on_Dalal_Street.JPG",
  };
}


// ── Worker entry point ────────────────────────────────────────────────────────
export default {
  async fetch(request, env, ctx) {
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

      // ── Inline query (stock name autocomplete) ───────────────────────────
      if (body.inline_query) {
        ctx.waitUntil(handleInlineQuery(body.inline_query, env));
        return new Response("OK");
      }

      // ── Callback query (inline keyboard button tap) ──────────────────────
      if (body.callback_query) {
        const cq = body.callback_query;
        const chatId = String(cq.message?.chat?.id || "");
        if (!env.TELEGRAM_CHAT_ID || chatId === env.TELEGRAM_CHAT_ID) {
          ctx.waitUntil(handleCallbackQuery(cq, env));
        }
        return new Response("OK");
      }

      // ── Regular chat message ─────────────────────────────────────────────
      const message = body.message;
      if (!message?.text) return new Response("OK");

      const chatId = String(message.chat.id);
      const text = message.text.trim();

      // Ignore messages from other chats.
      if (env.TELEGRAM_CHAT_ID && chatId !== env.TELEGRAM_CHAT_ID) {
        return new Response("OK");
      }

      if (text.startsWith("/")) {
        ctx.waitUntil(handleCommand(text, chatId, env));
      }
    } catch (err) {
      console.error("Worker error:", err);
    }

    return new Response("OK");
  },
};
