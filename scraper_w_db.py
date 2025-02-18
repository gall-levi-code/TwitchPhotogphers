from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
import requests
import os
import json
from database import SessionLocal, Streamer, UserList
from datetime import datetime, timezone
from sqlalchemy.orm import sessionmaker

load_dotenv()

# Environment Variables
CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL")

# Twitch Tags & Categories to Track
TAGS = ["photography", "lightroom", "photoshop"]
CATEGORIES = ["509660", "509658"]  # Art, Just Chatting

# Language Flag Mapping
LANGUAGE_FLAGS = {
    "en": "🇺🇸", "de": "🇩🇪", "fr": "🇫🇷", "es": "🇪🇸", "it": "🇮🇹",
    "ru": "🇷🇺", "ja": "🇯🇵", "ko": "🇰🇷", "zh": "🇨🇳", "pt": "🇵🇹",
    "nl": "🇳🇱", "sv": "🇸🇪", "fi": "🇫🇮", "pl": "🇵🇱", "tr": "🇹🇷"
}

# Database Session
db_session = SessionLocal()

# Get OAuth Token
def get_oauth_token():
    url = "https://id.twitch.tv/oauth2/token"
    params = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials"
    }
    response = requests.post(url, params=params)
    response.raise_for_status()
    return response.json()["access_token"]

# Get Channel Info
def get_channel_info(broadcaster_id, headers):
    url = "https://api.twitch.tv/helix/channels"
    params = {"broadcaster_id": broadcaster_id}
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()

# Check if a streamer is blacklisted
def is_blacklisted(broadcaster_id):
    user = db_session.query(UserList).filter_by(broadcaster_id=broadcaster_id).first()
    return user and not user.is_whitelisted  # Returns True if blacklisted

# Send a Discord Webhook for New Streamers
def send_discord_webhook(streamer_details):
    if not DISCORD_WEBHOOK:
        print("⚠️ Discord Webhook URL is missing.")
        return

    broadcaster_name, broadcaster_language, viewers, game_name, game_id, title, channel_tags, stream_url = streamer_details
    language_flag = LANGUAGE_FLAGS.get(broadcaster_language, "🏳️")

    embed = {
        "embeds": [
            {
                "title": title,
                "url": stream_url,
                "color": 0x9147FF,  # Twitch Purple
                "fields": [
                    {"name": "Streamer", "value": broadcaster_name, "inline": True},
                    {"name": "Language", "value": f"{language_flag} `{broadcaster_language}`", "inline": True},
                    {"name": "Viewers", "value": str(viewers), "inline": True},
                    {"name": "Category", "value": game_name, "inline": True},
                    {"name": "Tags", "value": channel_tags or "No tags", "inline": False}
                ],
                "footer": {"text": "Twitch Stream Alert", "icon_url": "https://static-cdn.jtvnw.net/ttv-static-metadata/twitch_logo3.jpg"}
            }
        ]
    }

    response = requests.post(DISCORD_WEBHOOK, json=embed)
    if response.status_code == 204:
        print(f"✅ Webhook sent for {broadcaster_name}")
    else:
        print(f"❌ Webhook Error: {response.status_code} - {response.text}")

# Update or insert streamer info
def update_streamer_info(broadcaster_id, details):
    if is_blacklisted(broadcaster_id):
        print(f"⚠️ Skipping blacklisted streamer: {broadcaster_id}")
        return

    streamer = db_session.query(Streamer).filter_by(broadcaster_id=broadcaster_id).first()
    is_new_streamer = streamer is None

    if streamer:
        print(f"🔄 Updating existing entry for {broadcaster_id}")
        streamer.broadcaster_name = details[0]
        streamer.broadcaster_language = details[1]
        streamer.viewers = details[2]
        streamer.game_name = details[3]
        streamer.game_id = details[4]
        streamer.title = details[5]
        streamer.tags = details[6].split(", ")  # Convert back to list
        streamer.stream_url = details[7]
        streamer.updated_at = datetime.now(timezone.utc)
    else:
        print(f"✅ Adding new streamer {broadcaster_id}")
        new_streamer = Streamer(
            broadcaster_id=broadcaster_id,
            broadcaster_name=details[0],
            broadcaster_language=details[1],
            viewers=details[2],
            game_name=details[3],
            game_id=details[4],
            title=details[5],
            tags=details[6].split(", "),
            stream_url=details[7],
            updated_at=datetime.now(timezone.utc)
        )
        db_session.add(new_streamer)

    db_session.commit()

    # Send webhook only for new streamers
    if is_new_streamer:
        send_discord_webhook(details)

# Lookup a user by Twitch Username or URL
def lookup_user(identifier):
    if identifier.startswith("https://twitch.tv/"):
        identifier = identifier.replace("https://twitch.tv/", "")

    user = db_session.query(Streamer).filter(
        (Streamer.broadcaster_name == identifier) |
        (Streamer.stream_url.endswith(identifier))
    ).first()

    if user:
        return {
            "broadcaster_id": user.broadcaster_id,
            "broadcaster_name": user.broadcaster_name,
            "language": user.broadcaster_language,
            "viewers": user.viewers,
            "game_name": user.game_name,
            "title": user.title,
            "tags": user.tags,
            "stream_url": user.stream_url,
            "updated_at": user.updated_at
        }
    else:
        return f"⚠️ No streamer found for '{identifier}'"

# Playwright Function to Scrape Twitch Data
def intercept_twitch_graphql(tag, headers):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        def handle_response(response):
            if "https://gql.twitch.tv/gql" in response.url and response.request.method == "POST":
                try:
                    json_data = response.json()
                    for entry in json_data:
                        if isinstance(entry, dict) and "data" in entry:
                            streams_data = entry["data"].get("streams", {}).get("edges", [])
                            for stream_entry in streams_data:
                                node = stream_entry.get("node", {})
                                assert node is not None

                                # Extract Broadcaster Info
                                broadcaster_id = node.get("broadcaster").get("id")
                                viewers = node.get("viewersCount") or 0
                                channel_info = get_channel_info(broadcaster_id, headers)["data"][0]

                                # Extract Data Fields
                                broadcaster_login = channel_info["broadcaster_login"]
                                broadcaster_name = channel_info["broadcaster_name"]
                                broadcaster_language = channel_info["broadcaster_language"]
                                game_name = channel_info["game_name"]
                                game_id = channel_info["game_id"]
                                title = channel_info["title"]
                                channel_tags = " ".join(channel_info['tags'])

                                # Filter by Category (Game ID)
                                if game_id in CATEGORIES:
                                    print(f"Streamer {broadcaster_name} is live in category {game_name}.")
                                    details = [
                                        broadcaster_name,
                                        broadcaster_language,
                                        viewers,
                                        game_name,
                                        game_id,
                                        title,
                                        channel_tags,
                                        f"https://twitch.tv/{broadcaster_login}"
                                    ]
                                    update_streamer_info(broadcaster_id, details)
                except json.JSONDecodeError:
                    print("Error decoding JSON response.")

        page.on("response", handle_response)
        page.goto(f"https://www.twitch.tv/directory/all/tags/{tag}")
        page.wait_for_load_state("networkidle")
        browser.close()

# Main Function
def main():
    token = get_oauth_token()
    headers = {"Client-ID": CLIENT_ID, "Authorization": f"Bearer {token}"}

    for tag in TAGS:
        print(f"🔎 Searching for streamers under '{tag}' tag...")
        intercept_twitch_graphql(tag, headers)

if __name__ == "__main__":
    main()
