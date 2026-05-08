import os
import sys
import json
import base64
import time
import requests
from flask import Flask, request

sys.stdout.reconfigure(line_buffering=True)

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
MY_GITHUB_TOKEN = os.environ["MY_GITHUB_TOKEN"]
GITHUB_REPO = os.environ["GITHUB_REPO"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
WATCHLIST_FILE = "watchlist.json"

MAGNIFICENT_SEVEN = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]

HELP_MESSAGE = (
    "🤖 *Stock Agent — Commands*\n\n"
    "📋 *LIST* — see your current watchlist\n\n"
    "➕ *BUY AAPL* — add a stock to your watchlist\n"
    "    _(also works with BOUGHT)_\n\n"
    "➖ *SELL AAPL* — remove a stock from your watchlist\n"
    "    _(also works with SOLD)_\n\n"
    "📰 *NEWS* — get the latest news for your stocks\n\n"
    "❓ *HELP* or *?* — show this message\n\n"
    "━━━━━━━━━━━━━━━\n"
    "🔔 *Automatic alerts:*\n"
    "• 📈 Daily stock report every weekday morning\n"
    "• 😱 Fear & Greed index alert when sentiment changes"
)

def get_watchlist():
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{WATCHLIST_FILE}"
    headers = {"Authorization": f"token {MY_GITHUB_TOKEN}"}
    r = requests.get(url, headers=headers).json()
    content = base64.b64decode(r["content"]).decode()
    sha = r["sha"]
    return json.loads(content), sha

def save_watchlist(watchlist, sha):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{WATCHLIST_FILE}"
    headers = {
        "Authorization": f"token {MY_GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    content = base64.b64encode(json.dumps(watchlist, indent=2).encode()).decode()
    response = requests.put(url, headers=headers, json={
        "message": "Update watchlist",
        "content": content,
        "sha": sha
    })
    print(f"💾 GitHub save status: {response.status_code}", flush=True)

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    })
    print(f"📤 Telegram send status: {r.status_code}", flush=True)

def run_claude_with_search(user_prompt, system_prompt):
    """Run Claude with web search in an agentic loop. Returns final text."""
    messages = [{"role": "user", "content": user_prompt}]

    for i in range(8):
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-5",
                "max_tokens": 800,
                "system": system_prompt,
                "tools": [{"type": "web_search_20250305", "name": "web_search"}],
                "messages": messages
            }
        )

        if response.status_code != 200:
            print(f"❌ API error {response.status_code}: {response.text}", flush=True)
            return None

        data = response.json()
        stop_reason = data.get("stop_reason")
        content_blocks = data.get("content", [])
        print(f"🔄 Iteration {i+1} stop_reason: {stop_reason}", flush=True)

        if stop_reason == "end_turn":
            text = " ".join(
                block["text"] for block in content_blocks
                if block.get("type") == "text"
            )
            return text if text.strip() else None

        # Handle tool use
        messages.append({"role": "assistant", "content": content_blocks})
        tool_results = [
            {
                "type": "tool_result",
                "tool_use_id": block["id"],
                "content": block.get("content", "")
            }
            for block in content_blocks
            if block.get("type") == "tool_use"
        ]

        if tool_results:
            messages.append({"role": "user", "content": tool_results})
        else:
            print("⚠️ No tool results found, stopping.", flush=True)
            break

    return None

def get_news_update(watchlist):
    strategic = [t for t in MAGNIFICENT_SEVEN if t not in watchlist]

    # --- Call 1: Portfolio news (detailed) ---
    portfolio_prompt = (
        f"Search for the latest news today for these stocks in my personal portfolio: {', '.join(watchlist)}. "
        f"For EACH stock, provide a detailed bullet point summary of any news, earnings, price movements, or developments. "
        f"Even minor news is important. Be thorough. Respond in English."
    )
    portfolio_system = (
        "You are a financial analyst. The user wants detailed news for their personal portfolio stocks. "
        "Search for recent news for each ticker and provide bullet point summaries. "
        "Be thorough — even minor developments matter for personal holdings."
    )

    # --- Call 2: Mag 7 significant events only ---
    strategic_prompt = (
        f"Search for today's news for these major market stocks: {', '.join(strategic)}. "
        f"ONLY report if there is a SIGNIFICANT event such as: quarterly earnings, "
        f"intraday price movement >5%, major regulatory changes, groundbreaking product launches, "
        f"or major sector macro events. "
        f"If there is no significant news for a stock, skip it entirely. "
        f"Respond in English with bullet points."
    )
    strategic_system = (
        "You are a financial analyst monitoring major market stocks. "
        "Only report on significant events — earnings, >5% price moves, major regulatory/product news, or macro sector events. "
        "Skip any stock with no significant news. Use bullet points."
    )

    print("🔍 Fetching portfolio news...", flush=True)
    portfolio_news = run_claude_with_search(portfolio_prompt, portfolio_system)

    print("⏳ Waiting 30 seconds before next call to avoid rate limits...", flush=True)
    time.sleep(30)

    print("🔍 Fetching strategic watchlist news...", flush=True)
    strategic_news = run_claude_with_search(strategic_prompt, strategic_system)

    # Build final message
    result = ""
    if portfolio_news:
        result += f"*📊 Your Portfolio:*\n{portfolio_news}"
    else:
        result += "*📊 Your Portfolio:*\nNo news found at the moment."

    if strategic_news and strategic_news.strip():
        result += f"\n\n*🌐 Market Leaders (Significant Events Only):*\n{strategic_news}"

    return result if result.strip() else "Could not find news at the moment. Please try again later."

@app.route("/")
def home():
    return "Bot is running!"

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    print(f"📩 Received: {json.dumps(data)}", flush=True)

    msg = data.get("message", {})
    text = msg.get("text", "").strip().upper()
    chat_id = str(msg.get("chat", {}).get("id", ""))

    if chat_id != str(TELEGRAM_CHAT_ID):
        print(f"❌ Ignoring message from unknown chat: {chat_id}", flush=True)
        return "ok"

    watchlist, sha = get_watchlist()
    print(f"📋 Current watchlist: {watchlist}", flush=True)

    words = text.split()
    command = words[0] if words else ""
    ticker = words[1] if len(words) > 1 else ""

    if command in ["BUY", "BOUGHT"] and ticker:
        if ticker not in watchlist:
            watchlist.append(ticker)
            save_watchlist(watchlist, sha)
            send_telegram(f"✅ Added *{ticker}* to your watchlist!\nCurrent list: {', '.join(watchlist)}")
        else:
            send_telegram(f"ℹ️ *{ticker}* is already in your watchlist.")

    elif command in ["SELL", "SOLD"] and ticker:
        if ticker in watchlist:
            watchlist.remove(ticker)
            save_watchlist(watchlist, sha)
            send_telegram(f"🗑️ Removed *{ticker}* from your watchlist.\nCurrent list: {', '.join(watchlist)}")
        else:
            send_telegram(f"ℹ️ *{ticker}* wasn't in your watchlist.")

    elif command == "LIST":
        send_telegram(f"📋 *Your current watchlist:*\n{', '.join(watchlist)}")

    elif command == "NEWS":
        send_telegram("🔍 Searching for the latest news for your portfolio, one moment...")
        news = get_news_update(watchlist)
        # Split into chunks if too long for Telegram (4096 char limit)
        chunks = [news[i:i+4000] for i in range(0, len(news), 4000)]
        send_telegram(f"📰 *News Update:*\n\n{chunks[0]}")
        for chunk in chunks[1:]:
            send_telegram(chunk)

    elif command in ["HELP", "?"]:
        send_telegram(HELP_MESSAGE)

    else:
        send_telegram("❓ Unknown command. Send *HELP* or *?* for a list of all commands.")

    return "ok"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
