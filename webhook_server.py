import os
import sys
import json
import base64
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

def call_claude(messages):
    """Call Claude API and return the full response data."""
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        },
        json={
            "model": "claude-sonnet-4-5",
            "max_tokens": 1024,
            "tools": [{"type": "web_search_20250305", "name": "web_search"}],
            "messages": messages
        }
    )
    return response.json()

def get_news_update(watchlist):
    """Use Claude with web search in an agentic loop until it returns a final text answer."""
    tickers = ", ".join(watchlist)
    messages = [{
        "role": "user",
        "content": (
            f"Search for the latest news today for these stocks: {tickers}. "
            f"For each stock, give one short sentence about the most important recent news or development. "
            f"Format as a simple list. Be very concise."
        )
    }]

    # Agentic loop — keep going until stop_reason is "end_turn" (no more tool calls)
    for _ in range(5):  # max 5 iterations to avoid infinite loop
        data = call_claude(messages)
        print(f"🤖 Claude response stop_reason: {data.get('stop_reason')}", flush=True)

        content_blocks = data.get("content", [])

        # If Claude is done, extract and return the final text
        if data.get("stop_reason") == "end_turn":
            text = " ".join(
                block["text"] for block in content_blocks
                if block.get("type") == "text"
            )
            return text if text else "There is no news."

        # Otherwise Claude used a tool — add its response to messages and continue
        # Add assistant's response to message history
        messages.append({"role": "assistant", "content": content_blocks})

        # Collect all tool results and add as a single user message
        tool_results = []
        for block in content_blocks:
            if block.get("type") == "tool_use":
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": block.get("content", "")
                })

        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    return "I wasn't able to find any news right now..."

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
        send_telegram(f"📋 Your current watchlist:\n{', '.join(watchlist)}")

    elif command == "NEWS":
        send_telegram("🔍 Hold on, searching for news...")
        news = get_news_update(watchlist)
        send_telegram(f"📰 *News Update:*\n\n{news}")

    else:
        send_telegram(
            "❓ Unknown command. Try:\n"
            "*BUY AAPL* — add a stock\n"
            "*SELL AAPL* — remove a stock\n"
            "*LIST* — see your watchlist\n"
            "*UPDATE* — get latest news for your stocks"
        )

    return "ok"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
