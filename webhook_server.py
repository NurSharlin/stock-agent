import os
import json
import base64
import requests
from flask import Flask, request

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
MY_GITHUB_TOKEN = os.environ["MY_GITHUB_TOKEN"]
GITHUB_REPO = os.environ["GITHUB_REPO"]
WATCHLIST_FILE = "watchlist.json"

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    msg = data.get("message", {})
    chat_id = str(msg.get("chat", {}).get("id", ""))
    print(f"INCOMING CHAT ID: '{chat_id}'")
    print(f"EXPECTED CHAT ID: '{TELEGRAM_CHAT_ID}'")

def get_watchlist():
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{WATCHLIST_FILE}"
    headers = {"Authorization": f"token {MY_GITHUB_TOKEN}"}
    r = requests.get(url, headers=headers).json()
    content = base64.b64decode(r["content"]).decode()
    return json.loads(content), r["sha"]

def save_watchlist(watchlist, sha):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{WATCHLIST_FILE}"
    headers = {"Authorization": f"token {MY_GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    content = base64.b64encode(json.dumps(watchlist, indent=2).encode()).decode()
    requests.put(url, headers=headers, json={
        "message": "Update watchlist",
        "content": content,
        "sha": sha
    })

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    })

@app.route(f"/webhook", methods=["POST"])
def webhook():
    data = request.json
    msg = data.get("message", {})
    text = msg.get("text", "").strip().upper()
    chat_id = str(msg.get("chat", {}).get("id", ""))

    if chat_id != str(TELEGRAM_CHAT_ID):
        return "ok"

    watchlist, sha = get_watchlist()
    changed = False

    if any(text.startswith(a) for a in ["BUY", "BOUGHT"]):
        ticker = text.split()[-1]
        if ticker not in watchlist:
            watchlist.append(ticker)
            changed = True
            send_telegram(f"✅ Added *{ticker}* to your watchlist!\nCurrent list: {', '.join(watchlist)}")
        else:
            send_telegram(f"ℹ️ *{ticker}* is already in your watchlist.")

    elif any(text.startswith(a) for a in ["SELL", "SOLD"]):
        ticker = text.split()[-1]
        if ticker in watchlist:
            watchlist.remove(ticker)
            changed = True
            send_telegram(f"🗑️ Removed *{ticker}* from your watchlist.\nCurrent list: {', '.join(watchlist)}")
        else:
            send_telegram(f"ℹ️ *{ticker}* wasn't in your watchlist.")

    elif text == "LIST":
        send_telegram(f"📋 Your current watchlist:\n{', '.join(watchlist)}")

    if changed:
        save_watchlist(watchlist, sha)

    return "ok"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
