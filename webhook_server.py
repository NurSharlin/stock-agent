import os
import sys
import json
import base64
import time
import requests
from datetime import datetime, timedelta
from flask import Flask, request

sys.stdout.reconfigure(line_buffering=True)

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
MY_GITHUB_TOKEN = os.environ["MY_GITHUB_TOKEN"]
GITHUB_REPO = os.environ["GITHUB_REPO"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
FINNHUB_API_KEY = os.environ["FINNHUB_API_KEY"]
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

# Track processed update IDs to prevent double-processing
processed_updates = set()
news_in_progress = False

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

def fetch_finnhub_news(ticker, days=3):
    """Fetch recent news headlines for a ticker from Finnhub."""
    to_date = datetime.today().strftime("%Y-%m-%d")
    from_date = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    url = "https://finnhub.io/api/v1/company-news"
    r = requests.get(url, params={
        "symbol": ticker,
        "from": from_date,
        "to": to_date,
        "token": FINNHUB_API_KEY
    })
    if r.status_code != 200:
        print(f"⚠️ Finnhub error for {ticker}: {r.status_code}", flush=True)
        return []
    articles = r.json()
    # Return top 5 headlines
    return [a["headline"] for a in articles[:5] if a.get("headline")]

def summarize_with_claude(news_data, is_portfolio=True):
    """Send news headlines to Claude for summarization."""
    if not news_data:
        return None

    if is_portfolio:
        system = (
            "You are a financial analyst. Summarize the latest news for the user's personal portfolio stocks. "
            "For each stock, provide a concise bullet point summary of the key developments. "
            "Even minor news matters. Be thorough but concise. Respond in English."
        )
        user = "Here are the latest news headlines for my portfolio stocks. Please summarize the key points for each:\n\n"
    else:
        system = (
            "You are a financial analyst. Review news headlines for major market stocks. "
            "ONLY highlight significant events: earnings reports, price moves >5%, major regulatory changes, "
            "groundbreaking product launches, or major sector macro events. "
            "Skip stocks with no significant news. Use bullet points. Respond in English."
        )
        user = "Here are recent headlines for major market stocks. Only report on significant events:\n\n"

    for ticker, headlines in news_data.items():
        if headlines:
            user += f"*{ticker}*:\n"
            for h in headlines:
                user += f"  - {h}\n"
            user += "\n"
        else:
            user += f"*{ticker}*: No recent news found.\n\n"

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        },
        json={
            "model": "claude-sonnet-4-5",
            "max_tokens": 1000,
            "system": system,
            "messages": [{"role": "user", "content": user}]
        }
    )

    if response.status_code != 200:
        print(f"❌ Claude API error {response.status_code}: {response.text}", flush=True)
        return None

    data = response.json()
    text = " ".join(
        block["text"] for block in data.get("content", [])
        if block.get("type") == "text"
    )
    return text.strip() if text.strip() else None

def get_news_update(watchlist):
    strategic = [t for t in MAGNIFICENT_SEVEN if t not in watchlist]

    # Fetch news from Finnhub for all tickers
    print("📡 Fetching news from Finnhub...", flush=True)
    portfolio_news = {}
    for ticker in watchlist:
        print(f"  → {ticker}", flush=True)
        portfolio_news[ticker] = fetch_finnhub_news(ticker)
        time.sleep(0.5)  # Respect Finnhub rate limits (60 req/min on free tier)

    strategic_news = {}
    for ticker in strategic:
        print(f"  → {ticker} (strategic)", flush=True)
        strategic_news[ticker] = fetch_finnhub_news(ticker)
        time.sleep(0.5)

    # Summarize with Claude
    print("🤖 Summarizing with Claude...", flush=True)
    portfolio_summary = summarize_with_claude(portfolio_news, is_portfolio=True)

    time.sleep(5)  # Small delay between Claude calls

    strategic_summary = summarize_with_claude(strategic_news, is_portfolio=False)

    # Build final message
    result = ""
    if portfolio_summary:
        result += f"*📊 Your Portfolio:*\n{portfolio_summary}"
    else:
        result += "*📊 Your Portfolio:*\nNo recent news found."

    if strategic_summary and strategic_summary.strip():
        result += f"\n\n*🌐 Market Leaders (Significant Events Only):*\n{strategic_summary}"

    return result if result.strip() else "Could not find news at the moment. Please try again later."

@app.route("/")
def home():
    return "Bot is running!"

@app.route("/webhook", methods=["POST"])
def webhook():
    global news_in_progress
    data = request.json
    print(f"📩 Received: {json.dumps(data)}", flush=True)

    # Deduplicate — ignore updates we've already processed
    update_id = data.get("update_id")
    if update_id in processed_updates:
        print(f"⚠️ Duplicate update {update_id}, ignoring.", flush=True)
        return "ok"
    processed_updates.add(update_id)
    if len(processed_updates) > 100:
        processed_updates.pop()

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
        if news_in_progress:
            send_telegram("⏳ Already fetching news, please wait...")
        else:
            news_in_progress = True
            try:
                send_telegram("🔍 Fetching latest news from Finnhub, one moment...")
                news = get_news_update(watchlist)
                chunks = [news[i:i+4000] for i in range(0, len(news), 4000)]
                send_telegram(f"📰 *News Update:*\n\n{chunks[0]}")
                for chunk in chunks[1:]:
                    send_telegram(chunk)
            finally:
                news_in_progress = False

    elif command in ["HELP", "?"]:
        send_telegram(HELP_MESSAGE)

    else:
        send_telegram("❓ Unknown command. Send *HELP* or *?* for a list of all commands.")

    return "ok"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
