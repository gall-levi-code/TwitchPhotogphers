import requests
import json
import random
import time
import itertools
import pprint

# Twitch API Credentials
CLIENT_ID = "dvyc46ccaug81xfb9rttq0z1sr117z"
CLIENT_SECRET = "bvsf5bkdd0s5dtt2d896f4t41trq7b"

# Keyword List

# Get OAuth token
def get_oauth_token():
    try:
        print("Fetching OAuth token...")
        url = "https://id.twitch.tv/oauth2/token"
        params = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "client_credentials"
        }
        response = requests.post(url, params=params)
        response.raise_for_status()  # Raises an HTTPError if the response code is 4xx/5xx
        data = response.json()
        print("OAuth token fetched successfully.")
        pprint.pprint(data)
        return data["access_token"]
    except requests.exceptions.RequestException as e:
        print(f"Error fetching OAuth token: {e}")
        return None

TOKEN = get_oauth_token()
if not TOKEN:
    print("Failed to get OAuth token, exiting.")
    exit(1)

photography_streamers = []
keywords = [
    "photography", "Lightroom", "Photoshop", "GIMP", "edit", "editing", "retouch", "color grading"
]

def has_relevant_tags(channel_tags, keywords):
    return any(keyword.lower() in (tag.lower() for tag in channel_tags) for keyword in keywords)

# Function to search for streams with photography-related keywords
def search_streams(keywords):
    headers = {
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {TOKEN}"
    }

    url = "https://api.twitch.tv/helix/search/channels"
    all_streams = []

    for keyword in keywords:
        try:
            print(f"Searching for streams with keyword: '{keyword}'...")
            params = {"query": keyword,"live_only": True,"first":100}
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()  # Raises an HTTPError if the response code is 4xx/5xx
            data = response.json()
            for channel in data.get("data", []):
                channel_tags = channel.get("tags", [])  # Ensure tags exist, default to empty list
                pprint.pp(channel_tags)
                if has_relevant_tags(channel_tags, keywords):
                    pprint.pp(channel)
                    all_streams.append(channel)

        except requests.exceptions.RequestException as e:
            print(f"Error fetching streams for keyword '{keyword}': {e}")

    print(f"Total streams found: {len(all_streams)}")
    print("Displaying results...")
    for streamer in all_streams:
        print(f"{streamer['display_name']} - {streamer['title']} - https://www.twitch.tv/{streamer['broadcaster_login']}")
    return all_streams

# Fetch and print photography-related streamers
print("Fetching photography-related streamers...")
results = search_streams(keywords)

if results:
    print("Displaying results...")
    for streamer in results:
        print(f"{streamer['display_name']} - {streamer['title']} - https://www.twitch.tv/{streamer['broadcaster_login']}")
else:
    print("No photography-related streamers found.")
