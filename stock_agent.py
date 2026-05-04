import os
import json
import yfinance as yf
import requests
import anthropic
from datetime import datetime

# --- Config ---
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPO = os.environ["GITHUB_REPO"]  # e.g. "yourusername/stock-agent"
LANGUAGE = os.environ.get("LANGUAGE", "Hebrew")  # Change to any language you want
WATCHLIST_FILE = "watchlist.json"

def get_watchlist():
    with open(WATCHLIST_FILE, "r") as f:
        return json.load(f)

def save_watchlist_to_github(watchlist):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{WATCHLIST_FILE}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}

    # Get current file SHA (required for updates)
    r = requests.get(url, headers=headers)
    sha = r.json()["sha"]

    import base64
    content = base64.b64encode(json.dumps(watchlist, indent=2).encode()).decode()
    requests.put(url, headers=headers, json={
        "message": "Update watchlist",
        "content": content,
        "sha": sha
    })

def get_stock_data(watchlist):
    lines = []
    for ticker in watchlist:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="2d")
        if len(hist) < 2:
            continue
        price = hist["Close"].iloc[-1]
        prev = hist["Close"].iloc[-2]
        change_pct = ((price - prev) / prev) * 100
        emoji = "🟢" if change_pct >= 0 else "🔴"
        lines.append(f"{emoji} {ticker}: ${price:.2f} ({change_pct:+.2f}%)")
    return "\n".join(lines)

def get_claude_analysis(stock_summary, language):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=400,
        messages=[{
            "role": "user",
            "content": (
                f"Here are today's stock movements:\n{stock_summary}\n\n"
                f"Give a brief 3-4 sentence analysis: what's notable, any patterns, "
                f"and one thing to watch. Be concise and clear. "
                f"IMPORTANT: Respond entirely in {language}."
            )
        }]
    )
    return message.content[0].text

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    })

def handle_telegram_updates():
    """Check for new messages and handle buy/sell commands."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset=-5"
    r = requests.get(url).json()
    watchlist = get_watchlist()
    changed = False

    for update in r.get("result", []):
        msg = update.get("message", {})
        text = msg.get("text", "").strip().upper()
        chat_id = str(msg.get("chat", {}).get("id", ""))

        if chat_id != str(TELEGRAM_CHAT_ID):
            continue

        # Handle: BUY AAPL or SOLD TSLA etc.
        for action in ["BUY", "BOUGHT"]:
            if text.startswith(action):
                ticker = text.split()[-1]
                if ticker not in watchlist:
                    watchlist.append(ticker)
                    changed = True
                    send_telegram(f"✅ Added *{ticker}* to your watchlist!\nCurrent list: {', '.join(watchlist)}")
                else:
                    send_telegram(f"ℹ️ *{ticker}* is already in your watchlist.")

        for action in ["SELL", "SOLD"]:
            if text.startswith(action):
                ticker = text.split()[-1]
                if ticker in watchlist:
                    watchlist.remove(ticker)
                    changed = True
                    send_telegram(f"🗑️ Removed *{ticker}* from your watchlist.\nCurrent list: {', '.join(watchlist)}")
                else:
                    send_telegram(f"ℹ️ *{ticker}* wasn't in your watchlist.")

        if text == "LIST":
            send_telegram(f"📋 Your current watchlist:\n{', '.join(watchlist)}")

    if changed:
        save_watchlist_to_github(watchlist)

    return watchlist

if __name__ == "__main__":
    mode = os.environ.get("MODE", "report")  # "report" or "listen"

    if mode == "listen":
        handle_telegram_updates()
    else:
        watchlist = handle_telegram_updates()  # process any pending commands first
        today = datetime.today().strftime("%B %d, %Y")
        stock_summary = get_stock_data(watchlist)
        analysis = get_claude_analysis(stock_summary, LANGUAGE)
        message = (
            f"📈 *Daily Stock Update — {today}*\n\n"
            f"{stock_summary}\n\n"
            f"🤖 *ניתוח:*\n{analysis}"
        )
        send_telegram(message)
        print("Sent successfully!")
