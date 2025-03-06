import discord, os, logging
from discord.ext import commands, tasks
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from discord import app_commands
from datetime import datetime, timezone
from database import Streamer, ServerSettings, SearchTags
from twitchFuncs import *

#Establish Environmental Variables
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = os.getenv("DISCORD_GUILD_ID")

# Database Setup
DATABASE_URL = "sqlite:///twitch_streamers.db"
engine = create_engine(DATABASE_URL, pool_size=20, max_overflow=30, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Logging
logging.basicConfig(level=logging.INFO)

class Client(commands.Bot):
    async def on_ready(self):
        logging.info(f"Logged in as {self.user} (ID: {self.user.id})")
        try:
            guild = discord.Object(id=GUILD_ID)
            synced = await self.tree.sync(guild=guild)
            logging.info(f"Synced {len(synced)} command(s)")
        except Exception as e:
            logging.info(f"Error syncing commands: {e}")

    async def on_message(self, message):
        if message.author == self.user:
            return

        if message.content.startswith("!test"):
            await message.channel.send(f"test command from {message.author}")


intents = discord.Intents.default()
intents.message_content = True
client = Client(command_prefix="!", intents=intents)

@tasks.loop(minutes=10)
async def check_for_new_streamers():
    logging.info("🔎 Checking for new streamers...")

    # ✅ Get all guilds from the database
    db_session = SessionLocal()
    guilds = db_session.query(SearchTags).all()
    db_session.close()

    logging.info(f"🔎 Found {len(guilds)} guilds to check.")

    for guild in guilds:
        guild_id = guild.guild_id

        # ✅ Get tags for the guild
        db_session = SessionLocal()
        search_entry = db_session.query(SearchTags).filter_by(guild_id=guild_id).first()
        tags = search_entry.search_tags if search_entry else []
        db_session.close()

        for iTag in tags:
            logging.info(f"🔎 Searching for streamers with tag: {iTag}")

            # ✅ Perform Twitch search (Assuming this is an async function)
            new_streamers, total_streamers = await twitch_search_by_tag(iTag)

            if total_streamers > 0:
                db_session = SessionLocal()
                approval_channel = db_session.query(ServerSettings).filter_by(guild_id=guild_id).first()
                db_session.close()

                if approval_channel:
                    channel = client.get_channel(int(approval_channel.approval_channel_id))
                    if not channel:
                        logging.info(f"⚠️ Could not find approval channel for guild {guild_id}")
                        continue

                    for found in new_streamers:
                        found = found.get('data')

                        # ✅ Open a session inside the loop, check, and close it after each query
                        db_session = SessionLocal()
                        existing_streamer = db_session.query(Streamer).filter_by(
                            guild_id=guild_id, broadcaster_id=found.get('broadcaster_id')
                        ).first()

                        if not existing_streamer:
                            embed = discord.Embed(title="📌 Pending Streamer Approval", color=0x9147FF)
                            embed.add_field(name="Streamer",
                                            value=f"[{found.get('broadcaster_name')}](https://twitch.tv/{found.get('broadcaster_login')})")
                            embed.set_thumbnail(url=found.get('profile_image_url'))

                            message = await channel.send(embed=embed)
                            await message.add_reaction("✅")  # Approve
                            await message.add_reaction("❌")  # Reject
                            await message.add_reaction("🤷")  # Maybe

                            new_pending = Streamer(
                                guild_id=guild_id,
                                broadcaster_id=found.get('broadcaster_id'),
                                broadcaster_name=found.get('broadcaster_name'),
                                stream_url=f"https://twitch.tv/{found.get('broadcaster_login')}",
                                status="pending",
                                message_id=str(message.id),
                                updated_at=datetime.now(timezone.utc),
                            )
                            db_session.add(new_pending)

                        db_session.commit()
                        db_session.close()  # ✅ Close session immediately after use


@client.event
async def on_ready():
    logging.info(f"✅ Logged in as {client.user}")
    check_for_new_streamers.start()  # Start the automatic search
    await client.tree.sync(guild=discord.Object(id=GUILD_ID))
    logging.info("✅ Slash commands synced!")


@client.tree.command(name="setup", description="Configure approval and broadcast channels",
                     guild=discord.Object(id=GUILD_ID))
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    approval_channel="Select the channel for streamer approvals",
    broadcast_channel="Select the channel where approved streamers will be announced"
)
async def setup(interaction: discord.Interaction, approval_channel: discord.TextChannel,
                broadcast_channel: discord.TextChannel):
    """Sets up approval and broadcast channels"""
    db_session = SessionLocal()
    guild_id = str(interaction.guild.id)

    # Update or create server settings
    server_settings = db_session.query(ServerSettings).filter_by(guild_id=guild_id).first()
    if not server_settings:
        server_settings = ServerSettings(guild_id=guild_id, approval_channel_id=str(approval_channel.id),
                                         broadcast_channel_id=str(broadcast_channel.id))
        db_session.add(server_settings)
    else:
        server_settings.approval_channel_id = str(approval_channel.id)
        server_settings.broadcast_channel_id = str(broadcast_channel.id)

    db_session.commit()
    await interaction.response.send_message(
        f"✅ **Setup Complete!**\n- **Approval Channel:** {approval_channel.mention}\n- **Broadcast Channel:** {broadcast_channel.mention}"
    )


@client.tree.command(name="settings", description="View current bot configuration for this server",
                     guild=discord.Object(id=GUILD_ID))
@app_commands.default_permissions(administrator=True)
async def settings(interaction: discord.Interaction):
    """Displays the current bot settings for the server"""
    db_session = SessionLocal()
    guild_id = str(interaction.guild.id)

    server_settings = db_session.query(ServerSettings).filter_by(guild_id=guild_id).first()

    if not server_settings:
        await interaction.response.send_message("⚠️ No settings found. Use `/setup` to configure the bot.")
        return

    approval_channel = server_settings.approval_channel_id
    broadcast_channel = server_settings.broadcast_channel_id

    embed = discord.Embed(title="⚙️ Approval and Broadcast Channel Settings", color=0x2F3136)
    embed.add_field(name="Approval Channel", value=f"<#{approval_channel}>", inline=False)
    embed.add_field(name="Broadcast Channel", value=f"<#{broadcast_channel}>", inline=False)

    await interaction.response.send_message(embed=embed)


@client.tree.command(name="streamer", description="Manage streamers (add or remove)", guild=discord.Object(id=GUILD_ID))
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    action="Choose an action: add or remove",
    info="Enter the Twitch username or URL"
)
async def streamer(interaction: discord.Interaction, action: str, info: str):
    if info.startswith("https://twitch.tv/") or info.startswith("https://www.twitch.tv/"):
        info = info.split("/")[-1]

    streamer_info = get_streamer_info(info)
    streamer_data = streamer_info.get('data')
    logging.info(streamer_data)
    if streamer_info.get('success') and streamer_data is not None and streamer_data.get('id') is not None:
        logging.info(f"{info} was found with data! Attempting to perform {action} action...")
        if action.lower() == 'add':
            login = streamer_data.get('login')
            display_name = streamer_data.get('display_name')
            broadcaster_id = streamer_data.get('id')
            profile_image_url = streamer_data.get('profile_image_url')
            broadcaster_type = streamer_data.get('broadcaster_type')
            description = streamer_data.get('description')

            # Initialize variables
            broadcaster_language = game_name = game_id = title = tags = None
            viewer_count = started_at = language = thumbnail_url = is_mature = None
            is_live = False
            live_for = "N/A"  # Default value

            if broadcaster_id:
                channel_info = get_channel_info(broadcaster_id)
                stream_info = get_stream_info(info)

                if channel_info.get('success'):
                    channel_data = channel_info.get('data')
                    broadcaster_language = channel_data.get('broadcaster_language')
                    game_name = channel_data.get('game_name')
                    game_id = channel_data.get('game_id')
                    title = channel_data.get('title')
                    tags = channel_data.get('tags')

                if stream_info.get('success'):
                    stream_data = stream_info.get('data')
                    viewer_count = stream_data.get('viewer_count')
                    started_at = stream_data.get('started_at')  # Example: '2025-03-01T03:25:00Z'
                    language = stream_data.get('language')
                    is_mature = stream_data.get('is_mature')

                    # Determine if streamer is live
                    is_live = viewer_count is not None and viewer_count > 0

                    # Calculate time live
                    if is_live and started_at:
                        start_time = datetime.strptime(started_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                        now_time = datetime.now(timezone.utc)
                        time_diff = now_time - start_time

                        # Convert to hours and minutes
                        hours, remainder = divmod(time_diff.seconds, 3600)
                        minutes, _ = divmod(remainder, 60)
                        live_for = f"{hours}h {minutes}m" if hours else f"{minutes}m"

                    # Replace {width} and {height} in thumbnail URL with 1920x1080
                    raw_thumbnail_url = stream_data.get('thumbnail_url', "")
                    if "{width}" in raw_thumbnail_url and "{height}" in raw_thumbnail_url:
                        thumbnail_url = raw_thumbnail_url.replace("{width}", "1920").replace("{height}", "1080")

            # Add 🔞 emoji if stream is marked as mature
            mature_flag = " 🔞" if is_mature else ""
            streamer_display = f"[{display_name}](https://twitch.tv/{login}){mature_flag}"

            # Set live/offline banner
            live_status = "🟢 **Live Now**" if is_live else "⚫ **Offline Now**"
            live_message = f"{live_status} | **Live for:** `{live_for}`" if is_live else live_status

            # Build the embed message
            embed = discord.Embed(
                description=f"**{description}**" if description else "No description available.",
                color=discord.Color.green() if is_live else discord.Color.dark_gray()
            )
            embed.set_thumbnail(
                url=profile_image_url if profile_image_url else "https://static.twitchcdn.net/assets/default-profile.png")
            embed.add_field(name="Streamer Name", value=streamer_display, inline=True)
            embed.add_field(name="Broadcaster Type", value=broadcaster_type.capitalize() if broadcaster_type else "N/A",
                            inline=True)

            if game_name and game_id:
                embed.add_field(name="Category", value=f"{game_name} ({game_id})", inline=True)
            elif game_name and not game_id:
                embed.add_field(name="Category", value=game_name, inline=True)

            if title:
                embed.add_field(name="Current Stream Title", value=title, inline=False)

            if viewer_count is not None:
                embed.add_field(name="Viewers", value=str(viewer_count), inline=True)

            if broadcaster_language:
                embed.add_field(name="Language", value=broadcaster_language.upper(), inline=True)

            if tags:
                embed.add_field(name="Tags", value=", ".join(tags) if tags else "None", inline=False)

            # Set the stream thumbnail as the embed image (if available)
            if is_live and thumbnail_url:
                embed.set_image(url=thumbnail_url)

            embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)

            # Update Database
            db_session = SessionLocal()

            server_settings = db_session.query(ServerSettings).filter_by(guild_id=interaction.guild_id).first()
            approval_channel = interaction.channel_id
            broadcast_channel = interaction.channel_id
            if server_settings:
                approval_channel = server_settings.approval_channel_id
                broadcast_channel = server_settings.broadcast_channel_id

            streamer_db = db_session.query(Streamer).filter_by(guild_id=interaction.guild_id,
                                                               broadcaster_id=broadcaster_id).first()
            if not streamer_db:
                logging.info(f"Streamer {broadcaster_id} not found in database. Creating a new entry...")
                streamer_db = Streamer(
                    guild_id=interaction.guild_id,
                    message_id=interaction.channel_id,
                    broadcaster_id=broadcaster_id,
                    broadcaster_name=login,
                    broadcaster_language=broadcaster_language,
                    viewers=viewer_count,
                    game_name=game_name,
                    game_id=game_id,
                    title=title,
                    tags=tags,  # Stores list of tags
                    stream_url=f"https://twitch.tv/{login}",
                    status="approved",
                    updated_at=datetime.now(timezone.utc),
                )
                db_session.add(streamer_db)
            else:
                streamer_db.status = "approved"
            logging.info(f"Attempting to create a message to send to <#{broadcast_channel}>")
            message = client.get_channel(int(broadcast_channel))
            logging.info(f"Attempting to send message: {live_message}")
            await message.send(content=live_message, embed=embed)
            streamer_db.message_id = message.id
            logging.info(message.id)
            db_session.commit()
            await interaction.response.send_message(f"Added {streamer_display} to the list of approved streamers.")
        elif action.lower() == 'remove':
            await interaction.response.send_message("Removed")
        elif action.lower() == 'pending':
            await interaction.response.send_message("Pending")
        else:
            await interaction.response.send_message("Nope")
    else:

        await interaction.response.send_message(
            f"Sorry we can't {action} your input '{info}'. It did not produce the proper response. Please try again.\n{streamer_info['data']}",
            ephemeral=True)
        # {
        #     'id': '735927359',
        #     'login': 'shotsbyajc',
        #     'display_name': 'ShotsByAJC',
        #     'type': '',
        #     'broadcaster_type': 'affiliate',
        #     'description': 'Are the shots photos, snipes, or drinks? Depends on the day.',
        #     'profile_image_url': 'https://static-cdn.jtvnw.net/jtv_user_pictures/39e8ffcf-4233-4bd8-abe8-c623c714552d-profile_image-300x300.png',
        #     'offline_image_url': '',
        #     'view_count': 0,
        #     'created_at': '2021-10-20T22:29:11Z'
        # }
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


@client.tree.command(name="search", description="View current bot configuration for this server",
                     guild=discord.Object(id=GUILD_ID))
@app_commands.default_permissions(administrator=True)
async def search(interaction: discord.Interaction, search_tag: str):
    """Searches Twitch for streamers under a tag and sends the results."""
    await interaction.response.defer()  # Avoids timeout while waiting for results

    # ✅ Await the async function to get the actual result
    # twitch_search_results = total_results = None
    twitch_search_results, total_results = await twitch_search_by_tag(search_tag)

    if total_results == 0:
        await interaction.followup.send(f"❌ No results found for '{search_tag}'")
        return
    display_names = ""
    for dict_result in twitch_search_results:
        result_info = dict_result.get('data')
        display_name = result_info.get('broadcaster_name')
        broadcaster_id = result_info.get('id')
        profile_image_url = result_info.get('profile_image_url')
        broadcaster_type = result_info.get('broadcaster_type')
        description = result_info.get('description')
        if display_name is not None:
            display_names += display_name + "\n"

    message = f"🟣 **Found {total_results} results for '{search_tag}'**\n{display_names}"
    logging.info(twitch_search_results)
    await interaction.followup.send(message)


@client.tree.command(name="tag", description="Manage tracked search tags", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(action="add, remove, or list tags", tag="The tag to add/remove (if applicable)")
async def tag(interaction: discord.Interaction, action: str, tag: str = None):
    db_session = SessionLocal()
    guild_id = str(interaction.guild_id)
    search_entry = db_session.query(SearchTags).filter_by(guild_id=guild_id).first()

    if action == "list":
        tags = search_entry.search_tags if search_entry else []
        await interaction.response.send_message(f"📌 **Tracked Tags:** {', '.join(tags) if tags else 'None'}")
        return

    if not tag:
        await interaction.response.send_message("⚠️ Please provide a tag.", ephemeral=True)
        return
    completed = ""
    if action == "add":
        if not search_entry:
            search_entry = SearchTags(guild_id=guild_id, search_tags=[tag])
            db_session.add(search_entry)
        else:
            if len(search_entry.search_tags) >= 5:
                await interaction.response.send_message(
                    "⚠️ You can only track **5 tags max**. Use /tag list to review your current tags. You may also remove tags with /tag remove *tag*.",
                    ephemeral=True)
                return
            if tag in search_entry.search_tags:
                await interaction.response.send_message(f"⚠️ The tag '{tag}' is already being tracked.", ephemeral=True)
                return
            search_entry.search_tags.append(tag)
            completed = "added"

    elif action == "remove":
        if search_entry and tag in search_entry.search_tags:
            search_entry.search_tags.remove(tag)
            completed = "removed"
        else:
            await interaction.response.send_message(f"⚠️ The tag '{tag}' isn't being tracked.", ephemeral=True)
            return

    db_session.commit()
    db_session.close()
    await interaction.response.send_message(f"✅ `{tag}` has been **{completed}**.")


@client.event
async def on_raw_reaction_add(payload):
    db_session = SessionLocal()
    message_id = str(payload.message_id)
    pending_streamer = db_session.query(Streamer).filter_by(message_id=message_id, status="pending").first()

    if not pending_streamer:
        return  # Ignore reactions on non-pending streamers

    guild = client.get_guild(payload.guild_id)
    channel = guild.get_channel(payload.channel_id) if guild else None
    message = await channel.fetch_message(payload.message_id) if channel else None

    if not message:
        return

    # Determine the new status based on the reaction
    if str(payload.emoji) == "✅":
        pending_streamer.status = "approved"
        new_content = f"✅ **{pending_streamer.broadcaster_name}** has been **approved**!"
    elif str(payload.emoji) == "❌":
        pending_streamer.status = "rejected"
        new_content = f"❌ **{pending_streamer.broadcaster_name}** has been **rejected**."
    else:
        return  # Ignore other reactions

    # Update the database
    db_session.commit()
    db_session.close()

    # Clear reactions and update message content
    await message.clear_reactions()
    await message.edit(content=new_content, embed=None)

client.run(TOKEN)