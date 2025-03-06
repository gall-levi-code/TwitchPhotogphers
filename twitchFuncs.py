import os, logging, requests
from playwright.async_api import async_playwright

# Logging
logging.basicConfig(level=logging.INFO)

#Establish Environmental Variables
from dotenv import load_dotenv
load_dotenv()

# Get Twitch Token
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
def get_tokens():
    # Twitch Token Get
    logging.info("Retrieving OAuth token...")
    url = "https://id.twitch.tv/oauth2/token"
    params = {"client_id": TWITCH_CLIENT_ID, "client_secret": TWITCH_CLIENT_SECRET, "grant_type": "client_credentials"}
    response = requests.post(url, params=params)
    response.raise_for_status()
    twitch_token = response.json()["access_token"]
    logging.info("✅ Twitch OAuth token acquired.")
    return twitch_token
TWITCH_TOKEN = get_tokens()
TWITCH_HEADERS = {
    "Client-ID": TWITCH_CLIENT_ID,
    "Authorization": f"Bearer {TWITCH_TOKEN}"
}
# ✅ Fetch Info from Twitch API
def get_streamer_info(streamer_name):
    """Fetch Twitch user data, handling errors gracefully."""
    logging.info(f"Fetching streamer info for broadcaster ID: {streamer_name}...")
    url = f"https://api.twitch.tv/helix/users?login={streamer_name}"

    try:
        response = requests.get(url, headers=TWITCH_HEADERS)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx, 5xx)
        data = response.json()

        if "data" in data and data["data"]:
            return {"success": True, "data": data["data"][0]}
        else:
            return {"success": False, "data": "No user data found"}

    except requests.exceptions.RequestException as e:
        return {"success": False, "data": str(e)}

def get_channel_info(broadcaster_id):
    logging.info(f"Fetching channel info for broadcaster ID: {broadcaster_id}...")
    url = "https://api.twitch.tv/helix/channels"
    params = {"broadcaster_id": broadcaster_id}
    try:
        response = requests.get(url, headers=TWITCH_HEADERS, params=params)
        response.raise_for_status()
        data = response.json()
        if "data" in data and data["data"]:
            return {"success": True, "data": data["data"][0]}
        else:
            return {"success": False, "data": "No channel data found"}
    except requests.exceptions.RequestException as e:
        return {"success": False, "data": str(e)}

def get_stream_info(broadcaster_login):
    logging.info(f"Fetching stream info for broadcaster login: {broadcaster_login}...")
    url = "https://api.twitch.tv/helix/streams"
    params = {"user_login": broadcaster_login}
    try:
        response = requests.get(url, headers=TWITCH_HEADERS, params=params)
        response.raise_for_status()
        data = response.json()
        if "data" in data and data["data"]:
            return {"success": True, "data": data["data"][0]}
        else:
            return {"success": False, "data": "No live stream data found"}
    except requests.exceptions.RequestException as e:
        return {"success": False, "data": str(e)}


async def twitch_search_by_tag(tag):
    """Asynchronously searches Twitch for streamers under a specific tag."""
    logging.info(f"🔎 Searching for streamers under '{tag}' tag...")
    total_streamers_found = 0
    streamers = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        async def handle_response(response):
            """Handles Twitch API GraphQL responses."""
            nonlocal total_streamers_found
            if "https://gql.twitch.tv/gql" in response.url and response.request.method == "POST":
                try:
                    json_data = await response.json()
                    # print(json_data)
                    for entry in json_data:
                        if isinstance(entry, dict) and "data" in entry:
                            streams_data = entry["data"].get("streams", {}).get("edges", [])
                            for stream_entry in streams_data:
                                node = stream_entry.get("node", {})
                                tags = node.get("freeformTags", None)
                                for iTag in tags:
                                    if tag.lower() == iTag.get('name').lower():
                                        broadcaster_id = node.get("broadcaster").get("id")
                                        streamers.append(get_channel_info(broadcaster_id))
                                        total_streamers_found += 1
                except Exception as e:
                    logging.error(f"Error processing Twitch API response: {e}")

        page.on("response", handle_response)

        await page.goto(f"https://www.twitch.tv/directory/all/tags/{tag}")
        await page.wait_for_load_state("networkidle")

        await browser.close()
        return streamers, total_streamers_found

    # return streamers, total_streamers_found
#
#
# def twitch_search_by_tag(tag):
#     logging.info(f"🔎 Searching for streamers under '{tag}' tag...")
#     total_streamers_found = 0
#     streamers = []
#     with async_playwright() as p:
#         browser = p.chromium.launch(headless=True)
#         page = browser.new_page()
#
#         def handle_response(response):
#             nonlocal total_streamers_found
#             if "https://gql.twitch.tv/gql" in response.url and response.request.method == "POST":
#                 try:
#                     json_data = response.json()
#                     for entry in json_data:
#                         if isinstance(entry, dict) and "data" in entry:
#                             streams_data = entry["data"].get("streams", {}).get("edges", [])
#                             for stream_entry in streams_data:
#                                 node = stream_entry.get("node", {})
#                                 assert node is not None
#
#                                 broadcaster_id = node.get("broadcaster").get("id")
#                                 streamers.append(broadcaster_id)
#                                 # viewers = node.get("viewersCount") or 0
#                                 # channel_info = get_channel_info(broadcaster_id)
#                                 #
#                                 # broadcaster_login = channel_info["broadcaster_login"]
#                                 # broadcaster_name = channel_info["broadcaster_name"]
#                                 # broadcaster_language = channel_info["broadcaster_language"]
#                                 # game_name = channel_info["game_name"]
#                                 # game_id = channel_info["game_id"]
#                                 # title = channel_info["title"]
#                                 # channel_tags = " ".join(channel_info['tags'])
#                                 #
#                                 # if game_id in CATEGORIES:
#                                 #     total_streamers_found += 1
#                                 #     logging.info(f"🎥 Found Streamer {broadcaster_name} ({broadcaster_language}) with {viewers} viewers.")
#                                 #     details = [
#                                 #         broadcaster_name,
#                                 #         broadcaster_language,
#                                 #         viewers,
#                                 #         game_name,
#                                 #         game_id,
#                                 #         title,
#                                 #         channel_tags,
#                                 #         f"https://twitch.tv/{broadcaster_login}"
#                                 #     ]
#                 except json.JSONDecodeError:
#                     logging.error("Error decoding JSON response.")
#
#         page.on("response", handle_response)
#         page.goto(f"https://www.twitch.tv/directory/all/tags/{tag}")
#         page.wait_for_load_state("networkidle")
#         browser.close()
#         return streamers, total_streamers_found