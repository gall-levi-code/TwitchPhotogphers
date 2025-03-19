import os, logging, requests, time
from datetime import datetime, timezone
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
    params = {
        "client_id": TWITCH_CLIENT_ID,
        "client_secret": TWITCH_CLIENT_SECRET,
        "grant_type": "client_credentials"
    }
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
def get_streamer_info(broadcaster_login):
    """Fetch Twitch user data, handling errors gracefully."""
    logging.info(f"Fetching streamer info for broadcaster_login: {broadcaster_login}...")
    url = f"https://api.twitch.tv/helix/users?login={broadcaster_login}"
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
    params = {
        "broadcaster_id": broadcaster_id
    }
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
    params = {
        "user_login": broadcaster_login,
        "type": 'all'
    }
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

def search_channels_by_term(search_term):
    logging.info(f"🔎 Searching live channels for '{search_term}'...")
    search_term = search_term.replace(" ","%20")
    url = "https://api.twitch.tv/helix/search/channels"
    params = {
        "query": search_term,
        "live_only": True,  # Ensure only live streams are returned
        "first": 100  # Limit to 20 results for testing; can adjust as needed
    }
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

async def search_live_channel_by_tag(tag):
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

class TwitchStreamer():
    def __init__(self, broadcaster_login):
        # Define user details
        self.broadcaster_id = None
        self.broadcaster_language = None
        self.broadcaster_login = broadcaster_login
        self.broadcaster_name = None
        self.broadcaster_type = None
        self.channel_tags = None
        self.created_at = None
        self.description = None
        self.game_id = None
        self.game_name = None
        self.is_live = None
        self.is_mature = None
        self.is_partnered = None
        self.is_verified = None
        self.live_for = None
        self.live_message = None
        self.live_status = None
        self.mature_flag = None
        self.offline_image_url = None
        self.profile_image_url = None
        self.started_at = None
        self.thumbnail_url = None
        self.title = None
        self.type = None
        self.url = f"https://www.twitch.tv/{self.broadcaster_login}"
        self.viewers = None
        self.streamer_display = None
        # Update user details

    def get_streamer_info(self):
        streamer_info = get_streamer_info(self.broadcaster_login)
        if streamer_info["success"]:
            print("Results from get_streamer_info:")
            print(streamer_info["data"])
            self.broadcaster_id = streamer_info["data"]["id"]
            self.broadcaster_name = streamer_info["data"]["display_name"]
            self.broadcaster_type = streamer_info["data"]["broadcaster_type"]
            self.created_at = streamer_info["data"]["created_at"]
            self.description = streamer_info["data"]["description"]
            self.offline_image_url = streamer_info["data"]["offline_image_url"]
            self.profile_image_url = streamer_info["data"]["profile_image_url"] or "https://static.twitchcdn.net/assets/default-profile.png"
            self.viewers = streamer_info["data"]["view_count"] or 0
            print(self.__dict__)
            return True
        else:
            return False

    def get_channel_info(self):
        # get_channel_info results
        # {
        #     'broadcaster_id': '735927359',
        #     'broadcaster_login': 'shotsbyajc',
        #     'broadcaster_name': 'ShotsByAJC',
        #     'broadcaster_language': 'en',
        #     'game_id': '509660',
        #     'game_name': 'Art',
        #     'title': 'Late Night Editing. PoE later? Maybe?',
        #     'delay': 0,
        #     'tags': ['AMA', 'ChillVibes', 'English', 'Photoshop', 'Editing', 'Photography'],
        #     'content_classification_labels': [],
        #     'is_branded_content': False
        # }
        channel_info = get_channel_info(self.broadcaster_id)
        if channel_info["success"]:
            print("Results from get_channel_info:")
            print(channel_info['data'])
            self.broadcaster_language = channel_info['data']["broadcaster_language"]
            self.game_id = channel_info['data']["game_id"]
            self.game_name = channel_info['data']["game_name"]
            self.title = channel_info['data']["title"]
            self.channel_tags = channel_info['data']["tags"]
            print(self.__dict__)
            return True
        else:
            return False

    def get_stream_info(self):
        # get_stream_info results
        # {
        #     'id': '316506378489',
        #     'user_id': '735927359',
        #     'user_login': 'shotsbyajc',
        #     'user_name': 'ShotsByAJC',
        #     'game_id': '509660',
        #     'game_name': 'Art',
        #     'type': 'live',
        #     'title': 'Late Night Editing. PoE later? Maybe?',
        #     'viewer_count': 5,
        #     'started_at': '2025-03-01T03:25:00Z',
        #     'language': 'en',
        #     'thumbnail_url': 'https://static-cdn.jtvnw.net/previews-ttv/live_user_shotsbyajc-{width}x{height}.jpg',
        #     'tag_ids': [],
        #     'tags': ['AMA', 'ChillVibes', 'English', 'Photoshop', 'Editing', 'Photography'],
        #     'is_mature': False
        # }
        stream_info = get_stream_info(self.broadcaster_login)
        if stream_info["success"]:
            print("Results from get_stream_info:")
            print(stream_info['data'])
            self.type = stream_info["data"]["type"]
            self.is_live = True if self.type == "live" else False
            self.started_at = stream_info["data"]["started_at"]
            self.is_mature = stream_info["data"]["is_mature"]
            if self.is_live and self.started_at:
                start_time = datetime.strptime(self.started_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                now_time = datetime.now(timezone.utc)
                time_diff = now_time - start_time
                # Convert to hours and minutes
                hours, remainder = divmod(time_diff.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                self.live_for = f"{hours}h {minutes}m" if hours else f"{minutes}m"
            self.mature_flag = " 🔞" if self.is_mature else ""
            self.live_status = "🟢 **Live Now**" if self.is_live else "⚫ **Offline Now**"
            self.streamer_display = f"[{self.broadcaster_name}](https://twitch.tv/{self.broadcaster_login}){self.mature_flag}"
            self.live_message = f"{self.live_status} | **Live for:** `{self.live_for}`" if self.is_live else self.live_status
            self.viewers = stream_info["data"]["viewer_count"]
            self.thumbnail_url = stream_info["data"]["thumbnail_url"]
            self.title = stream_info["data"]["title"]
            print(self.__dict__)
            return True
        else:
            print(stream_info["data"])
            return False

    def get_thumbnail_url(self, width=1920, height=1080):
        if self.thumbnail_url:
            return self.thumbnail_url.replace("{width}", f"{width}").replace("{height}", f"{height}")
        else:
            return None

    def update(self):
        self.get_streamer_info()
        print("sleeping for 1 second")
        time.sleep(1)
        self.get_channel_info()
        print("sleeping for 1 second")
        time.sleep(1)
        self.get_stream_info()
        print("sleeping for 1 second")
        time.sleep(1)

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


def main():
    test = TwitchStreamer("atlasvisuals")
    test.update()
    print(test.__dict__)


if __name__ == "__main__":
    main()