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
categories = [
    "509660", #art
    "509658" #Just Chatting
]
LANGUAGE_FLAGS = {
    "en": "🇺🇸", "de": "🇩🇪", "fr": "🇫🇷", "es": "🇪🇸", "it": "🇮🇹",
    "ru": "🇷🇺", "ja": "🇯🇵", "ko": "🇰🇷", "zh": "🇨🇳", "pt": "🇵🇹",
    "nl": "🇳🇱", "sv": "🇸🇪", "fi": "🇫🇮", "pl": "🇵🇱", "tr": "🇹🇷"
}
streamer_id = []
streamers = []

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

def get_game(game_id, headers):
    url = "https://api.twitch.tv/helix/games"
    params = {"id": game_id}
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    data = response.json()
    if data.get("data"):
        return data["data"][0]["name"]
    else:
        return None

def get_channel_info(broadcaster_id, headers):
    url = "https://api.twitch.tv/helix/channels"
    params = {"broadcaster_id": broadcaster_id}
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()

def intercept_twitch_graphql(tag, headers):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)  # Set to True for headless mode
        page = browser.new_page()
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
                                broadcaster_id = node.get("broadcaster", {}).get("id", "Unknown")
                                viewers = node.get("viewersCount","0")
                                if node.get("game"):
                                    game_id = node.get("game", {}).get("id", "Unknown")
                                else:
                                    game_id = None
                                if game_id and game_id in categories: ## Checks that the Game ID matches in the categories list
                                    if broadcaster_id and broadcaster_id != "Unknown":
                                        test = get_channel_info(broadcaster_id, headers)
                                        channel_info = test["data"][0]
                                        broadcaster_login = channel_info["broadcaster_login"]
                                        broadcaster_name = channel_info["broadcaster_name"]
                                        broadcaster_language = channel_info["broadcaster_language"]
                                        game_name = channel_info["game_name"]
                                        title = channel_info["title"]
                                        channel_tags = ", ".join(channel_info['tags'])
                                        pp(f"Streamer found! {broadcaster_name} (Language: {broadcaster_language}) is streaming with {viewers} viewer(s). They're streaming '{game_name}' ({game_id}): https://twitch.tv/{broadcaster_login}.\nTags: {channel_tags}.\nStream Title: {title}")
                                        streamers.append(broadcaster_id)
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
                except json.JSONDecodeError:
                    print("Error decoding JSON response.")

        # Intercept responses
        page.on("response", handle_response)

        # Open Twitch directory page
        page.goto(f"https://www.twitch.tv/directory/all/tags/{tag}")
        page.wait_for_load_state("networkidle")  # Ensure all requests are completed

        browser.close()


def main():

    # Step 1: Get the OAuth token
    token = get_oauth_token(CLIENT_ID, CLIENT_SECRET)
    headers = {
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {token}"
    }

    for tag in tags:
        pp(f"Searching for streamers that are in the '{tag}' tag. https://www.twitch.tv/directory/all/tags/{tag}")
        intercept_twitch_graphql(tag, headers)

if __name__ == "__main__":
    main()