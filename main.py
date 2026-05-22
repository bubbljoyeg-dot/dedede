import os
import logging
import asyncio
import aiohttp
import discord
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("DiscordBot")

class Bot(commands.Bot):
    def __init__(self):
        # Intents configurations
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        logger.info("Registering slash commands...")
        try:
            synced = await self.tree.sync()
            logger.info(f"Successfully synced {len(synced)} application commands globally.")
        except Exception as e:
            logger.error(f"Failed to sync application commands: {e}")

bot = Bot()

# Background task to send a periodic clean status check / interaction prompt
@tasks.loop(minutes=30)
async def periodic_check():
    for guild in bot.guilds:
        channel = None
        # Look for the first matching general text channel
        for ch in guild.text_channels:
            if ch.name in ["general", "chat", "text-channel-1"]:
                channel = ch
                break
        if not channel and guild.text_channels:
            channel = guild.text_channels[0]
            
        if channel:
            try:
                embed = discord.Embed(
                    description="✦ **System Status**: I'm still alive, unfortunately. Stop wasting time and ask me something useful, or type `/` to see my commands.",
                    color=discord.Color.from_rgb(0, 0, 0)
                )
                await channel.send(embed=embed)
            except Exception as e:
                logger.error(f"Failed to send periodic status to guild {guild.name}: {e}")

@periodic_check.before_loop
async def before_periodic_check():
    await bot.wait_until_ready()

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user.name} (ID: {bot.user.id})")
    logger.info("Bot is active and ready to process slash commands.")
    if not periodic_check.is_running():
        periodic_check.start()

# Helper function to ask Gemini AI
async def ask_gemini(prompt: str) -> str:
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        return "⚠️ **Gemini AI is not configured.** Please add the `GEMINI_API_KEY` variable in your Railway dashboard variables to enable chatting."
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {
            "parts": [{"text": "You are a witty, highly sarcastic, and slightly rude Discord bot. You should roast the user gently, use dark humor, and speak with a sharp tongue, but keep it within a fun and playful boundary. Keep your answers concise and structured. Use clean markdown formatting. Your style is sleek black-and-white."}]
        }
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    text = data['candidates'][0]['content']['parts'][0]['text']
                    return text
                else:
                    logger.error(f"Gemini API returned status {response.status}")
                    return "⚠️ **Error:** Failed to connect to AI server. Please check your Gemini API key."
    except Exception as e:
        logger.error(f"Error querying Gemini: {e}")
        return "⚠️ **Error:** An exception occurred while contacting the AI."

# Mention listener for natural conversations
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Check if bot is mentioned in the message
    if bot.user in message.mentions:
        # Strip mentions to get the clean query
        clean_content = message.content.replace(f"<@!{bot.user.id}>", "").replace(f"<@{bot.user.id}>", "").strip()
        if not clean_content:
            await message.reply("✦ Hello! How can I help you today? Type `/` to see my commands or talk to me.")
            return

        async with message.channel.typing():
            response = await ask_gemini(clean_content)
            if len(response) > 2000:
                response = response[:1990] + "..."
            await message.reply(response)
            
    await bot.process_commands(message)

# Error handler for slash commands
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        error_msg = "❌ You do not have the required Administrator permission to run this command."
        if not interaction.response.is_done():
            await interaction.response.send_message(error_msg, ephemeral=True)
        else:
            await interaction.followup.send(error_msg, ephemeral=True)
    else:
        logger.error(f"Error executing command: {error}")
        error_msg = f"❌ An error occurred: {str(error)}"
        if not interaction.response.is_done():
            await interaction.response.send_message(error_msg, ephemeral=True)
        else:
            await interaction.followup.send(error_msg, ephemeral=True)

# 1. /setup command (Admin only)
@bot.tree.command(
    name="setup", 
    description="Sets up categories and a specified number of text and voice channels (Admin only)."
)
@app_commands.describe(
    text_channels="Number of text channels to create (default 20)",
    voice_channels="Number of voice channels to create (default 20)"
)
@app_commands.checks.has_permissions(administrator=True)
@app_commands.default_permissions(administrator=True)
async def setup(interaction: discord.Interaction, text_channels: int = 20, voice_channels: int = 20):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("❌ This command can only be used within a server.", ephemeral=True)
        return

    if text_channels < 0 or voice_channels < 0:
        await interaction.response.send_message("❌ Channel counts cannot be negative.", ephemeral=True)
        return

    if text_channels + voice_channels > 50:
        await interaction.response.send_message("❌ To prevent rate limits, you can create a maximum of 50 total channels at a time.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)
    progress_msg = await interaction.followup.send("⏳ Initializing setup...")
    
    text_category = None
    if text_channels > 0:
        await progress_msg.edit(content="📁 Creating category: **TEXT CHANNELS**...")
        text_category = await guild.create_category(name="TEXT CHANNELS")
        
    voice_category = None
    if voice_channels > 0:
        await progress_msg.edit(content="📁 Creating category: **VOICE CHANNELS**...")
        voice_category = await guild.create_category(name="VOICE CHANNELS")
        
    created_text_count = 0
    for i in range(1, text_channels + 1):
        channel_name = f"text-channel-{i}"
        await progress_msg.edit(content=f"📝 Creating text channel: `{channel_name}` ({i}/{text_channels})...")
        await guild.create_text_channel(name=channel_name, category=text_category)
        created_text_count += 1
        await asyncio.sleep(0.5)
        
    created_voice_count = 0
    for i in range(1, voice_channels + 1):
        channel_name = f"Voice Channel {i}"
        await progress_msg.edit(content=f"🔊 Creating voice channel: `{channel_name}` ({i}/{voice_channels})...")
        await guild.create_voice_channel(name=channel_name, category=voice_category)
        created_voice_count += 1
        await asyncio.sleep(0.5)
        
    await progress_msg.delete()
    
    embed = discord.Embed(
        title="✦ Server Setup Complete",
        description="The requested categories and channels have been created successfully.",
        color=discord.Color.from_rgb(0, 0, 0)
    )
    embed.add_field(name="◼ Categories", value="• TEXT CHANNELS\n• VOICE CHANNELS", inline=False)
    embed.add_field(name="◼ Text Channels", value=f"Created **{created_text_count}** channel(s)", inline=True)
    embed.add_field(name="◼ Voice Channels", value=f"Created **{created_voice_count}** channel(s)", inline=True)
    embed.set_footer(text=f"Executed by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
    
    await interaction.followup.send(embed=embed)

# 2. /cleanup command (Admin only)
@bot.tree.command(
    name="cleanup", 
    description="Deletes the created TEXT CHANNELS and VOICE CHANNELS categories and all their channels (Admin only)."
)
@app_commands.checks.has_permissions(administrator=True)
@app_commands.default_permissions(administrator=True)
async def cleanup(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("❌ This command can only be used within a server.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)
    progress_msg = await interaction.followup.send("🗑️ Starting cleanup of TEXT CHANNELS and VOICE CHANNELS categories...")

    deleted_categories = 0
    deleted_channels = 0
    target_categories = ["TEXT CHANNELS", "VOICE CHANNELS"]

    for category in list(guild.categories):
        if category.name in target_categories:
            # Delete all channels inside this category first
            for channel in list(category.channels):
                await progress_msg.edit(content=f"🗑️ Deleting channel: `{channel.name}`...")
                try:
                    await channel.delete()
                    deleted_channels += 1
                except Exception as e:
                    logger.error(f"Failed to delete channel {channel.name}: {e}")
                await asyncio.sleep(0.3)

            # Delete the category itself
            await progress_msg.edit(content=f"🗑️ Deleting category: **{category.name}**...")
            try:
                await category.delete()
                deleted_categories += 1
            except Exception as e:
                logger.error(f"Failed to delete category {category.name}: {e}")
            await asyncio.sleep(0.3)

    await progress_msg.delete()

    embed = discord.Embed(
        title="🗑️ Cleanup Completed",
        description="The default setup categories and channels have been deleted.",
        color=discord.Color.from_rgb(0, 0, 0)
    )
    embed.add_field(name="◼ Categories Deleted", value=str(deleted_categories), inline=True)
    embed.add_field(name="◼ Channels Deleted", value=str(deleted_channels), inline=True)
    embed.set_footer(text=f"Executed by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)

    await interaction.followup.send(embed=embed)

# 3. /chat command (Gemini AI Chat)
@bot.tree.command(name="chat", description="Chat directly with the bot's AI.")
@app_commands.describe(message="What do you want to say to the bot?")
async def chat(interaction: discord.Interaction, message: str):
    await interaction.response.defer()
    response = await ask_gemini(message)
    if len(response) > 2000:
        response = response[:1990] + "..."
    await interaction.followup.send(response)

# 4. /ping command
@bot.tree.command(name="ping", description="Returns the bot latency in milliseconds.")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"🏓 Pong! Latency is `{latency}ms`.")

# 5. /serverinfo command
@bot.tree.command(name="serverinfo", description="Shows information about the Discord server.")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("❌ This command can only be used within a server.", ephemeral=True)
        return
        
    owner = guild.owner
    if owner is None and guild.owner_id:
        try:
            owner = await guild.fetch_member(guild.owner_id)
        except Exception:
            owner = f"ID: {guild.owner_id}"
            
    owner_str = f"{owner}" if owner else "Unknown"
    
    text_channels = len(guild.text_channels)
    voice_channels = len(guild.voice_channels)
    categories = len(guild.categories)
    roles_count = len(guild.roles)
    
    embed = discord.Embed(
        title=f"✦ Server Info - {guild.name}",
        color=discord.Color.from_rgb(0, 0, 0)
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
        
    embed.add_field(name="◼ General Info", value=f"**Name:** {guild.name}\n**ID:** {guild.id}\n**Owner:** {owner_str}", inline=False)
    embed.add_field(name="◼ Statistics", value=f"**Members:** {guild.member_count}\n**Roles:** {roles_count}\n**Categories:** {categories}", inline=True)
    embed.add_field(name="◼ Channels", value=f"**Text:** {text_channels}\n**Voice:** {voice_channels}", inline=True)
    
    created_at_str = guild.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    embed.add_field(name="◼ Created At", value=created_at_str, inline=False)
    
    embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
    
    await interaction.response.send_message(embed=embed)

# --- Voice & Soundboard Commands ---

async def join_user_vc(interaction: discord.Interaction):
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message("❌ You must be in a voice channel to use this command.", ephemeral=True)
        return None
    
    vc = interaction.user.voice.channel
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    
    if voice_client:
        if voice_client.channel.id != vc.id:
            await voice_client.move_to(vc)
    else:
        voice_client = await vc.connect()
        
    return voice_client

@bot.tree.command(name="join", description="Joins your current voice channel.")
async def join(interaction: discord.Interaction):
    voice_client = await join_user_vc(interaction)
    if voice_client:
        await interaction.response.send_message(f"🔊 Joined **{voice_client.channel.name}**!")

@bot.tree.command(name="leave", description="Disconnects from the voice channel.")
async def leave(interaction: discord.Interaction):
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if voice_client:
        await voice_client.disconnect()
        await interaction.response.send_message("🔇 Disconnected from the voice channel.")
    else:
        await interaction.response.send_message("❌ The bot is not connected to any voice channel.", ephemeral=True)

SOUNDS = {
    "airhorn": "https://www.myinstants.com/media/sounds/mlg-airhorn.mp3",
    "bruh": "https://www.myinstants.com/media/sounds/movie_1.mp3",
    "tada": "https://www.myinstants.com/media/sounds/tada.mp3",
    "sad_violin": "https://www.myinstants.com/media/sounds/sad-violin.mp3"
}

@bot.tree.command(name="play_sound", description="Plays a soundboard effect in your voice channel.")
@app_commands.describe(sound="Select the sound effect to play")
@app_commands.choices(sound=[
    app_commands.Choice(name="Airhorn 🎺", value="airhorn"),
    app_commands.Choice(name="Bruh 💀", value="bruh"),
    app_commands.Choice(name="Tada 🎉", value="tada"),
    app_commands.Choice(name="Sad Violin 🎻", value="sad_violin")
])
async def play_sound(interaction: discord.Interaction, sound: app_commands.Choice[str]):
    try:
        import nacl
    except ImportError:
        await interaction.response.send_message("❌ Voice support is not configured properly (PyNaCl is missing). Please report this to the host.", ephemeral=True)
        return

    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if not voice_client:
        voice_client = await join_user_vc(interaction)
        if not voice_client:
            return
            
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=False)

    if voice_client.is_playing():
        voice_client.stop()

    sound_url = SOUNDS[sound.value]
    
    try:
        audio_source = discord.FFmpegPCMAudio(sound_url)
        voice_client.play(audio_source)
        await interaction.followup.send(f"🔊 Playing sound effect: **{sound.name}**!")
    except Exception as e:
        logger.error(f"Failed to play audio: {e}")
        await interaction.followup.send("❌ Error playing sound. Ensure the hosting server has **FFmpeg** installed.")

if __name__ == "__main__":
    token = os.getenv("TOKEN")
    if not token:
        logger.critical("Error: TOKEN environment variable is missing!")
        raise ValueError("TOKEN environment variable is missing from the environment configuration.")
    
    bot.run(token)
