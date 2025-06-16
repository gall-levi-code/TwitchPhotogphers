from datetime import datetime, timezone

import discord, logging, os
from discord import app_commands
from discord.ext import commands, tasks
# Establish Environmental Variables
from dotenv import load_dotenv

from database import db_manager, Streamer, ServerSettings, SearchTags
from twitchFuncs import TwitchStreamer, search_live_channel_by_tag, search_channels_by_term, get_multiple_streams

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = os.getenv("DISCORD_GUILD_ID")

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
        check_for_new_streamers.start()
    async def on_message(self, message):
        if message.author == self.user:
            return
        if message.content.startswith("!test"):
            await message.channel.send(f"test command from {message.author}")

intents = discord.Intents.default()
intents.message_content = True
client = Client(command_prefix="!", intents=intents)

def get_channel_settings(guild_id):
    server_settings = db_manager.get_one(ServerSettings, guild_id=guild_id)
    if not server_settings:
        return None
    else:
        return server_settings

def embed_streamer_standard(input_streamer):
    embed = discord.Embed(
        description=f"**{input_streamer.description}**" if input_streamer.description else "No description available.",
        color=discord.Color.green() if input_streamer.is_live else discord.Color.dark_gray()
    )
    embed.set_thumbnail(
        url=input_streamer.profile_image_url if input_streamer.profile_image_url else "https://static.twitchcdn.net/assets/default-profile.png")
    embed.add_field(name="Streamer Name", value=input_streamer.streamer_display, inline=True)
    embed.add_field(name="Broadcaster Type", value=input_streamer.broadcaster_type.capitalize() if input_streamer.broadcaster_type else "N/A",
                    inline=True)
    if input_streamer.game_name and input_streamer.game_id:
        embed.add_field(name="Category", value=f"{input_streamer.game_name} ({input_streamer.game_id})", inline=True)
    elif input_streamer.game_name and not input_streamer.game_id:
        embed.add_field(name="Category", value=input_streamer.game_name, inline=True)

    if input_streamer.title:
        embed.add_field(name="Current Stream Title", value=input_streamer.title, inline=False)
    if input_streamer.viewers is not None:
        embed.add_field(name="Viewers", value=str(input_streamer.viewers), inline=True)
    if input_streamer.broadcaster_language:
        embed.add_field(name="Language", value=input_streamer.broadcaster_language.upper(), inline=True)
    if input_streamer.channel_tags:
        embed.add_field(name="Tags", value=", ".join(input_streamer.channel_tags) if input_streamer.channel_tags else "None", inline=False)
    if input_streamer.is_live and input_streamer.thumbnail_url:
        embed.set_image(url=input_streamer.get_thumbnail_url(width="1920", height="1080"))
    return embed

def embed_streamer_pending(input_streamer):
    # Build Embed
    embed = discord.Embed(
        title=f"📌 Pending Streamer Approval: {input_streamer.broadcaster_name}",
        description=f"**{input_streamer.title}**",
        color=discord.Color.orange()
    )
    embed.set_thumbnail(url=input_streamer.profile_image_url)

    embed.add_field(name="Streamer", value=input_streamer.streamer_display, inline=True)
    embed.add_field(name="Viewers", value=f"`{input_streamer.viewers}`", inline=True)
    language = input_streamer.broadcaster_language or "N/A"
    embed.add_field(name="Language", value=f"`{language.upper()}`", inline=True)

    embed.add_field(name="Game", value=f"{input_streamer.game_name} (`{input_streamer.game_id}`)", inline=True)
    embed.add_field(name="Live Status", value=f"{input_streamer.live_status} | **Live for:** `{input_streamer.live_for}`",
                    inline=True)

    if input_streamer.channel_tags:
        embed.add_field(name="Tags", value=", ".join(input_streamer.channel_tags), inline=False)

    embed.set_footer(text="React to approve or reject this streamer")

    # Set stream thumbnail if live
    if input_streamer.is_live and input_streamer.thumbnail_url:
        embed.set_image(url=input_streamer.get_thumbnail_url(width=1920, height=1080))

    return embed

async def send_approved_streamer_broadcast(channel, embed, live_message):
    if channel is None:
        logging.error("send_approved_streamer_broadcast: Received None for channel.")
        return

    try:
        logging.info(f"Sending broadcast to channel {channel.id}")
        await channel.send(content=live_message, embed=embed)
        logging.info("Broadcast message successfully sent.")
    except Exception as e:
        logging.error(f"Failed to send broadcast message: {e}")

async def add_approved_streamer(channel: discord.TextChannel,guild_id, broadcaster_login):
    info = TwitchStreamer(broadcaster_login=broadcaster_login)
    embed = embed_streamer_standard(info)
    await send_approved_streamer_broadcast(channel, embed, info.live_message)
    # Create Streamer DB entry
    existing_streamer = db_manager.get_one(Streamer, guild_id=guild_id, broadcaster_id=info.broadcaster_id)
    if not existing_streamer:
        new_approved = Streamer(
            guild_id=guild_id,
            broadcaster_id=info.broadcaster_id,
            broadcaster_name=info.broadcaster_name,
            stream_url=info.url,
            status="approved",
            message_id="",
            updated_at=datetime.now(timezone.utc),
            broadcaster_language=info.broadcaster_language,
            viewers=info.viewers,
            game_name=info.game_name,
            game_id=info.game_id,
            title=info.title,
            tags=info.channel_tags,
        )
        db_manager.add_entry(new_approved)


async def send_pending_streamer_message(channel: discord.TextChannel, input_streamer):
    """Sends a detailed embed message for streamer approval."""
    embed = embed_streamer_pending(input_streamer)
    # Send Message & Add Reactions
    message = await channel.send(embed=embed)
    await message.add_reaction("✅")  # Approve
    await message.add_reaction("❌")  # Reject
    await message.add_reaction("🤷")  # Maybe

    return message

async def add_pending_approval(channel: discord.TextChannel,guild_id, broadcaster_login):
    info = TwitchStreamer(broadcaster_login=broadcaster_login)
    existing_streamer = db_manager.get_one(Streamer, guild_id=guild_id, broadcaster_id=info.broadcaster_id)
    if not existing_streamer:
        logging.info("STREAMER WAS NOT FOUND ADDING PENDING APPROVAL")
        message = await send_pending_streamer_message(channel, input_streamer=info)
        new_pending = Streamer(
            guild_id=guild_id,
            broadcaster_id=info.broadcaster_id,
            broadcaster_name=info.broadcaster_name,
            stream_url=info.url,
            status="pending",
            message_id=str(message.id),
            updated_at=datetime.now(timezone.utc),
            broadcaster_language=info.broadcaster_language,
            viewers=info.viewers,
            game_name=info.game_name,
            game_id=info.game_id,
            title=info.title,
            tags=info.channel_tags,
        )
        db_manager.add_entry(new_pending)

@client.tree.command(
    name="setup",
    description="Configure approval and broadcast channels",
    guild=discord.Object(id=GUILD_ID)
)
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    approval_channel="Select the channel for streamer approvals",
    broadcast_channel="Select the channel where approved streamers will be announced"
)
async def setup(interaction: discord.Interaction, approval_channel: discord.TextChannel,
                broadcast_channel: discord.TextChannel):
    """Sets up approval and broadcast channels"""

    guild_id = str(interaction.guild.id)
    server_settings = get_channel_settings(guild_id)

    if not server_settings:
        server_settings = ServerSettings(
            guild_id=guild_id,
            approval_channel_id=str(approval_channel.id),
            broadcast_channel_id=str(broadcast_channel.id)
        )
    else:
        server_settings.approval_channel_id = str(approval_channel.id)
        server_settings.broadcast_channel_id = str(broadcast_channel.id)
    db_manager.add_entry(server_settings)
    await interaction.response.send_message(
        f"✅ **Setup Complete!**\n- **Approval Channel:** {approval_channel.mention}\n- **Broadcast Channel:** {broadcast_channel.mention}"
    )

@client.tree.command(name="settings", description="View current bot configuration for this server",
                     guild=discord.Object(id=GUILD_ID))
@app_commands.default_permissions(administrator=True)
async def settings(interaction: discord.Interaction):
    """Displays the current bot settings for the server"""

    guild_id = str(interaction.guild.id)
    server_settings = get_channel_settings(guild_id)

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
@app_commands.choices(
    action=[
        app_commands.Choice(name="Add", value="approved"),
        app_commands.Choice(name="Remove", value="rejected"),
        app_commands.Choice(name="Pending", value="pending")
    ]
)
async def streamer(interaction: discord.Interaction, action: str, info: str):
    if info.startswith("https://twitch.tv/") or info.startswith("https://www.twitch.tv/"):
        info = info.split("/")[-1]
    i = TwitchStreamer(info)
    if i.broadcaster_id:
        """With valid information we check for corrections and perform accordingly, additionally we verify if there's a broadcaster id"""
        logging.info(f"{info} was found with data! Attempting to perform {action} action...")
        """We gather the current guild settings for channel information."""
        server_settings = db_manager.get_one(ServerSettings,guild_id=interaction.guild_id)
        """We set defaults here to ensure there's a fallback."""
        approval_channel = interaction.channel_id
        broadcast_channel = interaction.channel_id
        message = ""
        if server_settings:
            approval_channel = server_settings.approval_channel_id
            broadcast_channel = server_settings.broadcast_channel_id
        # Generation of a discord channel object to perform message sending and gather message.id afterward for db actions.
        channel = client.get_channel(int(broadcast_channel))
        # Collection of current DB item if found.
        streamer_db = db_manager.get_one(Streamer, guild_id=interaction.guild_id, broadcaster_id=i.broadcaster_id)
        # create the embed to send / manipulate
        embed = embed_streamer_standard(i)

        # Update message title or create a pending message for actions.
        if action == 'approved':
            # embed.title(f'Adding the streamer: {info}')
            message = await send_approved_streamer_broadcast(broadcast_channel,interaction.guild_id,i.broadcaster_name)
            await interaction.response.send_message(f"Streamer approved: {info}")
        elif action == 'rejected':
            # embed.title(f'Rejecting the streamer: {info}')
            await interaction.response.send_message(f"Streamer rejected: {info}")
        elif action == 'pending':
            channel = client.get_channel(int(approval_channel))
            message = await send_pending_streamer_message(channel, i)
            await interaction.response.send_message(f"Sending {info} to pending approvals. [Click to view](https://discord.com/channels/{interaction.guild_id}/{channel.id}/{message.id})")

        if streamer_db:
            streamer_db.status = action
            streamer_db.updated_at = datetime.now(timezone.utc)
            db_manager.add_entry(streamer_db)
        else:
            logging.info(f"Streamer {i.broadcaster_id} not found in database. Creating a new entry...")
            streamer_entry = Streamer(
                guild_id=interaction.guild_id,
                message_id=interaction.id,
                broadcaster_id=i.broadcaster_id,
                broadcaster_name=i.broadcaster_login,
                broadcaster_language=i.broadcaster_language,
                viewers=i.viewers,
                game_name=i.game_name,
                game_id=i.game_id,
                title=i.title,
                tags=i.channel_tags,  # Stores list of tags
                stream_url=f"https://twitch.tv/{i.broadcaster_login}",
                status=action,
                updated_at=datetime.now(timezone.utc),
            )
            db_manager.add_entry(streamer_entry)
    else:
        await interaction.response.send_message(
            f"Sorry we can't {action} your input '{info}'. It did not produce the proper response. Please try again.",
            ephemeral=True)

@client.tree.command(name="status", description="List off the current pending / approved / rejected counts.", guild=discord.Object(id=GUILD_ID))
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    action="Choose an action: add or remove",
)
@app_commands.choices(action=[
    app_commands.Choice(name="Pending", value="pending"),
    app_commands.Choice(name="Approved", value="approved"),
    app_commands.Choice(name="Rejected", value="rejected"),
    app_commands.Choice(name="List", value="list")
])
async def status(interaction: discord.Interaction, action: str):
    streamers = db_manager.get_all(Streamer,guild_id=interaction.guild_id)
    available_actions = ["pending", "approved", "rejected"]
    pending_count = 0
    approved_count = 0
    rejected_count = 0
    streamer_count = 0
    display_names = ""
    if action.lower() == "list":
        for iStreamer in streamers:
            if iStreamer.status == "pending":
                pending_count += 1
            elif iStreamer.status == "approved":
                approved_count += 1
            elif iStreamer.status == "rejected":
                rejected_count += 1
        await interaction.response.send_message(f"Our current counts are:\nPending: {pending_count}\nApproved: {approved_count}\nRejected: {rejected_count}\nTotal: {pending_count+approved_count+rejected_count}")
    elif action.lower() in available_actions:
        for iStreamer in streamers:
            if iStreamer.status == action.lower():
                streamer_count += 1
                display_names += f"https://twitch.tv/{iStreamer.broadcaster_name}" + "\n"
        if len(display_names) > 2000:
            await interaction.response.send_message(f"**{action.lower()}** streamers: {streamer_count}")
        else:
            await interaction.response.send_message(f"Here's our list of {action.lower()} streamers(Total: {streamer_count}):```\n{display_names}```")

class SearchListView(discord.ui.View):
    def __init__(self, data, author_id):
        super().__init__(timeout=60)
        self.data = data.get('data')
        self.author_id = author_id
        self.current_page = 0
        self.i = None
        self.embed = self.generate_embed()

    def server_settings(self, guild_id):
        channel_settings = get_channel_settings(guild_id)
        return channel_settings

    def generate_embed(self):
        self.i = TwitchStreamer(self.data[self.current_page].get('broadcaster_login'))
        embed = embed_streamer_standard(self.i)
        embed.set_footer(text=f"Page {self.current_page + 1} of {len(self.data) + 1}")
        return embed

    async def update_message(self, interaction: discord.Interaction):
        self.embed = self.generate_embed()
        await interaction.response.edit_message(embed=self.embed, view=self)

    async def add_streamer(self, interaction: discord.Interaction):
        server_settings = get_channel_settings(interaction.guild_id)
        if server_settings:
            channel = client.get_channel(server_settings.broadcast_channel_id)
        else:
            channel = interaction.channel
        await add_approved_streamer(channel,interaction.guild_id,self.i.broadcaster_name)
        await interaction.response.edit_message(
            content=f"{self.i.broadcaster_name} has been added, sending broadcast: ",embed=None, view=None)

    async def remove_streamer(self, interaction: discord.Interaction):
        streamer_info = db_manager.get_one(Streamer,guild_id=interaction.guild_id,broadcaster_id=self.i.broadcaster_id)
        if streamer_info:
            streamer_info.status = "rejected"
            db_manager.add_entry(streamer_info)
            await interaction.response.edit_message(
                content=f"{self.i.broadcaster_name} has been removed...", embed=None, view=None)
        else:
            new_approved = Streamer(
                guild_id=interaction.guild_id,
                broadcaster_id=self.i.broadcaster_id,
                broadcaster_name=self.i.broadcaster_name,
                stream_url=self.i.url,
                status="rejected",
                message_id="",
                updated_at=datetime.now(timezone.utc),
                broadcaster_language=self.i.broadcaster_language,
                viewers=self.i.viewers,
                game_name=self.i.game_name,
                game_id=self.i.game_id,
                title=self.i.title,
                tags=self.i.channel_tags,
            )
            db_manager.add_entry(new_approved)
            await interaction.response.edit_message(
                content=f"{self.i.broadcaster_name} has been added to the DB, and rejected.", embed=None, view=None)

    async def pending_streamer(self, interaction: discord.Interaction):
        server_settings = get_channel_settings(interaction.guild_id)
        if server_settings:
            channel = client.get_channel(server_settings.broadcast_channel_id)
        else:
            channel = interaction.channel
        message = await send_pending_streamer_message(channel, self.i)
        await interaction.response.edit_message(
            content=f"Sending {self.i.broadcaster_name} to pending approvals. [Click to view](https://discord.com/channels/{interaction.guild_id}/{channel.id}/{message.id})", embed=None, view=None)

    @discord.ui.button(label="⬅️", style=discord.ButtonStyle.secondary, disabled=True)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("⚠️ You can't control this pagination.", ephemeral=True)
        self.current_page -= 1
        self.next_button.disabled = False
        if self.current_page == 0:
            self.previous_button.disabled = True
        await self.update_message(interaction)


    @discord.ui.button(label="✅", style=discord.ButtonStyle.green, disabled=False)
    async def add_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("⚠️ You can't control this pagination.", ephemeral=True)
        await self.add_streamer(interaction)

    @discord.ui.button(label="❌", style=discord.ButtonStyle.red, disabled=False)
    async def remove_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("⚠️ You can't control this pagination.", ephemeral=True)
        await self.remove_streamer(interaction)

    @discord.ui.button(label="🤷", style=discord.ButtonStyle.green, disabled=False)
    async def pending_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("⚠️ You can't control this pagination.", ephemeral=True)
        await self.pending_streamer(interaction)


    @discord.ui.button(label="➡️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("⚠️ You can't control this pagination.", ephemeral=True)
        self.current_page += 1
        self.previous_button.disabled = False
        if self.current_page >= (len(self.data)-1):
            self.next_button.disabled = True
        await self.update_message(interaction)

@client.tree.command(name="search", description="View current bot configuration for this server",
                     guild=discord.Object(id=GUILD_ID))
@app_commands.default_permissions(administrator=True)
async def search(interaction: discord.Interaction, search_term: str):
    """Searches Twitch for a particular term."""
    # await interaction.response.defer()
    results = search_channels_by_term(search_term)
    if results.get('success'):
        view = SearchListView(results, interaction.user.id)
        await interaction.response.send_message(embed=view.embed, view=view)
    else:
        await interaction.response.send_message(f"Sorry no results found for {search_term}")


@client.event
async def on_raw_reaction_add(payload):
    message_id = str(payload.message_id)
    pending_streamer = db_manager.get_one(Streamer, guild_id=payload.guild_id, message_id=message_id, status="pending")

    if not pending_streamer:
        return  # Ignore reactions on non-pending streamers

    guild = client.get_guild(payload.guild_id)
    channel = guild.get_channel(payload.channel_id) if guild else None
    message = await channel.fetch_message(payload.message_id) if channel else None

    if not message:
        logging.error("Message not found or inaccessible.")
        return

    server_settings = db_manager.get_one(ServerSettings, guild_id=payload.guild_id)
    broadcast_channel = None

    if server_settings and server_settings.broadcast_channel_id:
        broadcast_channel = client.get_channel(int(server_settings.broadcast_channel_id))

    # Fallback if broadcast_channel is not defined or accessible
    if not broadcast_channel:
        broadcast_channel = channel
        logging.warning("Using fallback broadcast channel (current channel).")

    if str(payload.emoji) == "✅":
        pending_streamer.status = "approved"
        new_content = f"✅ **{pending_streamer.broadcaster_name}** has been **approved**!"
        logging.info(f"Approving streamer {pending_streamer.broadcaster_name}")
        await add_approved_streamer(broadcast_channel, payload.guild_id, pending_streamer.broadcaster_name)

    elif str(payload.emoji) == "❌":
        pending_streamer.status = "rejected"
        new_content = f"❌ **{pending_streamer.broadcaster_name}** has been **rejected**."
        logging.info(f"Rejecting streamer {pending_streamer.broadcaster_name}")
    else:
        return  # Ignore other reactions

    pending_streamer.updated_at = datetime.now(timezone.utc)
    db_manager.add_entry(pending_streamer)

    await message.clear_reactions()
    await message.edit(content=new_content, embed=None)


@client.tree.command(name="live", description="Shows all currently live streamers from approved list",
                     guild=discord.Object(id=GUILD_ID))
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    streamer_type="List who's live: approved or pending")
@app_commands.choices(
    streamer_type=[
        app_commands.Choice(name="Approved", value="approved"),
        app_commands.Choice(name="Pending", value="pending")
    ]
)
async def live(interaction: discord.Interaction, streamer_type: str):
    # Defer the response immediately to avoid timeout
    await interaction.response.defer(thinking=True)

    # Get all approved streamers for this guild
    approved = db_manager.get_all(Streamer, guild_id=interaction.guild_id, status=f"{streamer_type}")

    if not approved:
        await interaction.followup.send(f"No '{streamer_type}' streamers found.")
        return

    # Extract broadcaster IDs and names
    live_streams = []

    # Process in batches of 100 (Twitch API limit)
    for i in range(0, len(approved), 100):
        batch = approved[i:i + 100]

        # Get IDs for this batch
        broadcaster_ids = [streamer.broadcaster_id for streamer in batch]

        # Call our new function from twitchFuncs
        result = get_multiple_streams(user_ids=broadcaster_ids)

        if result["success"]:
            for stream in result["data"]:
                # Format each live stream
                stream_url = f"https://twitch.tv/{stream['user_login']}"
                stream_title = stream['title']
                viewer_count = stream['viewer_count']
                live_streams.append(f"{stream_url} - {stream_title} ({viewer_count} viewers)")

    # Send the results
    if not live_streams:
        await interaction.followup.send("No streamers are currently live.")
        return

    # Split into chunks if too long
    message_chunks = []
    current_chunk = f"**Currently Live Streamers who are *{streamer_type.upper()}*:**\n"

    for stream in live_streams:
        if len(current_chunk) + len(stream) + 2 > 2000:  # Discord message limit
            message_chunks.append(current_chunk)
            current_chunk = stream + "\n"
        else:
            current_chunk += stream + "\n"

    if current_chunk:
        message_chunks.append(current_chunk)

    # Send first message as followup
    await interaction.followup.send(message_chunks[0],suppress_embeds=True)

    # Send additional messages if needed
    for chunk in message_chunks[1:]:
        await interaction.channel.send(chunk,suppress_embeds=True)

class TagGroup(app_commands.Group):
    """Manages tracked search tags with subcommands"""

    @app_commands.command(name="add", description="Add a tag to track")
    async def add(self, interaction: discord.Interaction, tag: str):
        """Adds a tag to the list of tracked tags"""
        guild_id = str(interaction.guild_id)
        tags_list = db_manager.get_one(SearchTags, guild_id=guild_id)

        if not tags_list:
            tags_list = SearchTags(guild_id=guild_id, search_tags=[tag])
            db_manager.add_entry(tags_list)
        else:
            if len(tags_list.search_tags) >= 5:
                await interaction.response.send_message(
                    "⚠️ You can only track **5 tags max**. Use `/tag list` to review your current tags. Remove tags with `/tag remove <tag>`.",
                    ephemeral=True)
                return
            if tag in tags_list.search_tags:
                await interaction.response.send_message(f"⚠️ The tag '{tag}' is already being tracked.",
                                                        ephemeral=True)
                return

        updated_tags = tags_list.search_tags + [tag]
        tags_list.search_tags = updated_tags
        db_manager.add_entry(tags_list)
        await interaction.response.send_message(f"✅ `{tag}` has been **added**.")
        check_for_new_streamers.restart()


    @app_commands.command(name="remove", description="Remove a tracked tag")
    async def remove(self, interaction: discord.Interaction, tag: str):
        """Removes a tag from the tracked list"""
        guild_id = str(interaction.guild_id)
        tags_list = db_manager.get_one(SearchTags, guild_id=guild_id)

        if tags_list and tag in tags_list.search_tags:
            updated_tags = [t for t in tags_list.search_tags if t != tag]
            tags_list.search_tags = updated_tags
            db_manager.add_entry(tags_list)
            await interaction.response.send_message(f"✅ `{tag}` has been **removed**.")
        else:
            await interaction.response.send_message(f"⚠️ The tag '{tag}' isn't being tracked.", ephemeral=True)
            return
        check_for_new_streamers.restart()

    @app_commands.command(name="list", description="List all tracked tags")
    async def list(self, interaction: discord.Interaction):
        """Displays all tracked tags"""
        guild_id = str(interaction.guild_id)
        tags_list = db_manager.get_one(SearchTags, guild_id=guild_id)
        tags = tags_list.search_tags if tags_list else []

        await interaction.response.send_message(f"📌 **Tracked Tags:** {', '.join(tags) if tags else 'None'}")

client.tree.add_command(TagGroup(name="tag"),guild=discord.Object(id=GUILD_ID))

@tasks.loop(minutes=10)
async def check_for_new_streamers():
    """Runs every 10 minutes to search for streamers and add them to pending."""
    logging.info("🔎 Checking for new streamers...")

    guilds = db_manager.get_all(SearchTags)
    logging.info(f"🔎 Found {len(guilds)} guilds to check.")

    for guild in guilds:
        guild_id = guild.guild_id
        tags = guild.search_tags if guild else []
        logging.info(tags)
        for iTag in tags:
            logging.info(f"🔎 Searching for streamers with tag: {iTag}")

            new_streamers, total_streamers = await search_live_channel_by_tag(iTag)

            if total_streamers > 0:
                approval_channel = db_manager.get_one(ServerSettings, guild_id=guild_id)

                if approval_channel:
                    channel = client.get_channel(int(approval_channel.approval_channel_id))
                    if not channel:
                        logging.info(f"⚠️ Could not find approval channel for guild {guild_id}")
                        continue

                    for found in new_streamers:
                        broadcaster_login = found['data']['broadcaster_login']
                        await add_pending_approval(channel,guild_id,broadcaster_login)
        logging.info("*** SEARCH COMPLETED ***")

client.run(TOKEN)