from playwright.sync_api import sync_playwright
from pprint import pp as pp
from dotenv import load_dotenv
import requests
import os
import json

load_dotenv()

CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL")

tags = ["photography","lightroom","photoshop"]
LANGUAGE_FLAGS = {
    "en": "🇺🇸", "de": "🇩🇪", "fr": "🇫🇷", "es": "🇪🇸", "it": "🇮🇹",
    "ru": "🇷🇺", "ja": "🇯🇵", "ko": "🇰🇷", "zh": "🇨🇳", "pt": "🇵🇹",
    "nl": "🇳🇱", "sv": "🇸🇪", "fi": "🇫🇮", "pl": "🇵🇱", "tr": "🇹🇷"
}
streamer_id = []

def intercept_twitch_graphql(tag):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)  # Set to True for headless mode
        page = browser.new_page()
        streamers = []
        # Function to handle API responses
        def handle_response(response):
            if "https://gql.twitch.tv/gql" in response.url and response.request.method == "POST":
                try:
                    json_data = response.json()  # Parse JSON response

                    for entry in json_data:
                        if isinstance(entry, dict) and "data" in entry:
                            streams_data = entry["data"].get("streams", {}).get("edges", [])  # Adjusting based on actual structure

                            for stream_entry in streams_data:
                                node = stream_entry.get("node", {})  # Twitch sometimes nests data in "node"
                                title = node.get("title", "N/A")
                                id = node.get("id","N/A")
                                broadcaster = node.get("broadcaster", {}).get("displayName", "Unknown")
                                broadcaster_id = node.get("broadcaster", {}).get("id", "Unknown")
                                broadcaster_language = node.get("broadcaster", {}).get("broadcaster_language")
                                viewers = node.get("viewersCount", 0)
                                category = node.get("game", {}).get("name", "N/A")
                                game_id = node.get("game_id")
                                # Create the Discord Embed Message
                                stream_url = f"https://twitch.tv/{broadcaster}"
                                embed = {
                                    "embeds": [
                                        {
                                            "title": title,
                                            "url": stream_url,
                                            "color": 0x9147FF,  # Twitch Purple
                                            "fields": [
                                                {"name": "Streamer", "value": broadcaster, "inline": True},
                                                {"name": "Language", "value": f":flag_{broadcaster_language}:", "inline": True},
                                                {"name": "Watch Now", "value": f"[Click Here]({stream_url})", "inline": False},
                                                # {"name": "Tags", "value": ", ".join(node.get("tags")) if node.get("tags") else "No tags", "inline": False}
                                            ],
                                            "footer": {"text": "Twitch Stream Alert", "icon_url": "https://static-cdn.jtvnw.net/ttv-static-metadata/twitch_logo3.jpg"}
                                        }
                                    ]
                                }

                                # Send Webhook to Discord
                                # response = requests.post(DISCORD_WEBHOOK, json=embed)
                                # if response.status_code == 204:
                                #     print("✅ Webhook sent successfully!")
                                # else:
                                #     print(f"❌ Error: {response.status_code} - {response.text}")
                                # Example Node Structure
                                # {'id': '316602781437',
                                #  'title': 'Welcome to Impulse!',
                                #  'viewersCount': 1,
                                #  'previewImageURL': 'https://static-cdn.jtvnw.net/previews-ttv/live_user_impulsecamerastore-440x248.jpg',
                                #  'broadcaster': {'id': '1214813764',
                                #                  'login': 'impulsecamerastore',
                                #                  'displayName': 'impulsecamerastore',
                                #                  'profileImageURL': 'https://static-cdn.jtvnw.net/jtv_user_pictures/72321b87-e5bd-49be-896e-ca4e70023b90-profile_image-50x50.png',
                                #                  'primaryColorHex': '1C7BE1',
                                #                  'roles': {'isPartner': False,
                                #                            'isParticipatingDJ': False,
                                #                            '__typename': 'UserRoles'},
                                #                  '__typename': 'User'},
                                #  'freeformTags': [{'id': 'fft:CHANNEL:1214813764:0',
                                #                    'name': 'English',
                                #                    '__typename': 'FreeformTag'},
                                #                   {'id': 'fft:CHANNEL:1214813764:1',
                                #                    'name': 'camera',
                                #                    '__typename': 'FreeformTag'},
                                #                   {'id': 'fft:CHANNEL:1214813764:2',
                                #                    'name': 'photography',
                                #                    '__typename': 'FreeformTag'},
                                #                   {'id': 'fft:CHANNEL:1214813764:3',
                                #                    'name': 'videography',
                                #                    '__typename': 'FreeformTag'}],
                                #  'game': {'id': '509658',
                                #           'slug': 'just-chatting',
                                #           'name': 'Just Chatting',
                                #           'displayName': 'Just Chatting',
                                #           'boxArtURL': 'https://static-cdn.jtvnw.net/ttv-boxart/509658-40x56.jpg',
                                #           '__typename': 'Game'},
                                #  'type': 'live',
                                #  'previewThumbnailProperties': {'blurReason': 'BLUR_NOT_REQUIRED',
                                #                                 '__typename': 'PreviewThumbnailProperties'},
                                #  '__typename': 'Stream'}

                                if game_id and game_id == "509660":
                                    pp(node)
                                    streamers.append(broadcaster_id)

                except json.JSONDecodeError:
                    print("Error decoding JSON response.")

        # Intercept responses
        page.on("response", handle_response)

        # Open Twitch directory page
        page.goto(f"https://www.twitch.tv/directory/all/tags/{tag}")
        page.wait_for_load_state("networkidle")  # Ensure all requests are completed

        browser.close()
        pp(streamers)
        streamer_id.append(streamers)
        return streamers


def get_oauth_token(client_id, client_secret):
    url = "https://id.twitch.tv/oauth2/token"
    params = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials"
    }
    response = requests.post(url, params=params)
    response.raise_for_status()
    data = response.json()
    return data["access_token"]

def get_user_id(streamer_name, headers):
    url = "https://api.twitch.tv/helix/users"
    params = {"login": streamer_name}
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    data = response.json()
    if data.get("data"):
        return data["data"][0]["id"]
    else:
        return None

def get_channel_info(broadcaster_id, headers):
    url = "https://api.twitch.tv/helix/channels"
    params = {"broadcaster_id": broadcaster_id}
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()

def main():
    # Step 1: Get the OAuth token
    token = get_oauth_token(CLIENT_ID, CLIENT_SECRET)
    headers = {
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {token}"
    }

    for tag in tags:
        intercept_twitch_graphql(tag)

    for broadcaster_id in streamer_id:
        channel_data = get_channel_info(broadcaster_id, headers)
        print(f"Streamer: {broadcaster_id}")
        # The API returns a JSON with a 'data' key containing a list of tag objects.
        for info in channel_data.get("data", []):
            pp(info)
            print(f"Tag ID: {info.get('tags')}, Title: {info.get('title')}")
        print("-" * 40)

if __name__ == "__main__":
    main()