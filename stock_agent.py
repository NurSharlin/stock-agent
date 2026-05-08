import os
import json
import base64
import yfinance as yf
import requests
import anthropic
from datetime import datetime

# --- Config ---
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
MY_GITHUB_TOKEN = os.environ["MY_GITHUB_TOKEN"]
GITHUB_REPO = os.environ["GITHUB_REPO"]
LANGUAGE = os.environ.get("LANGUAGE", "English")
WATCHLIST_FILE = "watchlist.json"

def get_watchlist():
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{WATCHLIST_FILE}"
    headers = {"Authorization": f"token {MY_GITHUB_TOKEN}"}
    r = requests.get(url, headers=headers).json()
    content = base64.b64decode(r["content"]).decode()
    return json.loads(content)

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

if __name__ == "__main__":
    watchlist = get_watchlist()
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
