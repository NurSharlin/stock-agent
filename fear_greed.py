import os
import json
import base64
import requests

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
MY_GITHUB_TOKEN = os.environ["MY_GITHUB_TOKEN"]
GITHUB_REPO = os.environ["GITHUB_REPO"]
STATE_FILE = "fear_greed_state.json"

# Map normalized lowercase keys to display labels + emojis
CATEGORY_MAP = {
    "extreme fear":  ("Extreme Fear",  "😱"),
    "fear":          ("Fear",          "😨"),
    "neutral":       ("Neutral",       "😐"),
    "greed":         ("Greed",         "🤑"),
    "extreme greed": ("Extreme Greed", "🚀"),
}

def get_fear_greed():
    """Fetch current Fear & Greed index from alternative.me API."""
    r = requests.get("https://api.alternative.me/fng/?limit=1")
    data = r.json()
    entry = data["data"][0]
    score = int(entry["value"])
    raw_label = entry["value_classification"]
    print(f"Raw API label: '{raw_label}'", flush=True)

    # Normalize to lowercase for lookup
    normalized = raw_label.strip().lower()
    label, emoji = CATEGORY_MAP.get(normalized, (raw_label.title(), "📊"))
    return score, label, emoji

def get_state():
    """Get previously saved category from GitHub."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{STATE_FILE}"
    headers = {"Authorization": f"token {MY_GITHUB_TOKEN}"}
    r = requests.get(url, headers=headers)
    if r.status_code == 404:
        return None, None
    data = r.json()
    content = json.loads(base64.b64decode(data["content"]).decode())
    return content.get("category"), data["sha"]

def save_state(category, sha):
    """Save current category to GitHub."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{STATE_FILE}"
    headers = {
        "Authorization": f"token {MY_GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    content = base64.b64encode(json.dumps({"category": category}, indent=2).encode()).decode()
    body = {"message": "Update fear & greed state", "content": content}
    if sha:
        body["sha"] = sha
    requests.put(url, headers=headers, json=body)

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    })

if __name__ == "__main__":
    score, current_category, current_emoji = get_fear_greed()
    previous_category, sha = get_state()

    print(f"Current: {current_emoji} {current_category} ({score}) | Previous: {previous_category}")

    if previous_category is None:
        print("First run, saving initial state.")
        save_state(current_category, sha)
        send_telegram(
            f"✅ *Fear & Greed Index initialized!*\n\n"
            f"Current sentiment: {current_emoji} *{current_category}*\n"
            f"Score: *{score}/100*\n\n"
            f"You'll be notified when the category changes."
        )

    elif current_category != previous_category:
        _, prev_emoji = CATEGORY_MAP.get(previous_category.strip().lower(), (previous_category, "📊"))
        message = (
            f"🚨 *Fear & Greed Index Alert!*\n\n"
            f"Market sentiment has shifted:\n\n"
            f"{prev_emoji} *{previous_category}* → {current_emoji} *{current_category}*\n\n"
            f"Current score: *{score}/100*"
        )
        send_telegram(message)
        save_state(current_category, sha)
        print("Category changed! Notified and saved.")

    else:
        print(f"No change ({current_category}, score: {score}). No notification sent.")
