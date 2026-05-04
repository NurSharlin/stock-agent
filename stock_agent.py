import os
import yfinance as yf
import requests
import anthropic
from datetime import datetime

# --- Config ---
WATCHLIST = ["AAPL", "NVDA", "TSLA", "MSFT"]  # Edit these!
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

def get_stock_data():
    lines = []
    for ticker in WATCHLIST:
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

def get_claude_analysis(stock_summary):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=400,
        messages=[{
            "role": "user",
            "content": (
                f"Here are today's stock movements:\n{stock_summary}\n\n"
                "Give a brief 3-4 sentence analysis: what's notable, any patterns, "
                "and one thing to watch. Be concise and clear."
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
    today = datetime.today().strftime("%B %d, %Y")
    stock_summary = get_stock_data()
    analysis = get_claude_analysis(stock_summary)

    message = (
        f"📈 *Daily Stock Update — {today}*\n\n"
        f"{stock_summary}\n\n"
        f"🤖 *Claude's Take:*\n{analysis}"
    )
    send_telegram(message)
    print("Sent successfully!")
