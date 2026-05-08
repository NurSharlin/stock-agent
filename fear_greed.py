import os
import json
import base64
import requests

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
MY_GITHUB_TOKEN = os.environ["MY_GITHUB_TOKEN"]
GITHUB_REPO = os.environ["GITHUB_REPO"]
STATE_FILE = "fear_greed_state.json"

CATEGORY_EMOJI = {
    "Extreme Fear": "😱",
    "Fear": "😨",
    "Neutral": "😐",
    "Greed": "🤑",
    "Extreme Greed": "🚀"
}

def get_fear_greed():
    """Fetch current Fear & Greed index from CNN API."""
    r = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata")
    data = r.json()
    score = round(data["fear_and_greed"]["score"])
    category = data["fear_and_greed"]["rating"].title()  # e.g. "extreme fear" -> "Extreme Fear"
    return score, category

def get_state():
    """Get previously saved category from GitHub."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{STATE_FILE}"
    headers = {"Authorization": f"token {MY_GITHUB_TOKEN}"}
    r = requests.get(url, headers=headers)
    if r.status_code == 404:
        return None, None  # file doesn't exist yet
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
    score, current_category = get_fear_greed()
    previous_category, sha = get_state()

    print(f"Current: {current_category} ({score}) | Previous: {previous_category}")

    if previous_category is None:
        # First run — just save the state, no notification
        print("First run, saving initial state.")
        save_state(current_category, sha)

    elif current_category != previous_category:
        # Category changed — notify!
        prev_emoji = CATEGORY_EMOJI.get(previous_category, "")
        curr_emoji = CATEGORY_EMOJI.get(current_category, "")
        message = (
            f"🚨 *Fear & Greed Index Alert!*\n\n"
            f"The market sentiment has shifted:\n\n"
            f"{prev_emoji} *{previous_category}* → {curr_emoji} *{current_category}*\n\n"
            f"Current score: *{score}/100*"
        )
        send_telegram(message)
        save_state(current_category, sha)
        print(f"Category changed! Notified and saved.")

    else:
        print(f"No change in category ({current_category}). No notification sent.")
