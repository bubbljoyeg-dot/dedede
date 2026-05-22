import os
import logging
import asyncio
import discord
from discord.ext import commands
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

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user.name} (ID: {bot.user.id})")
    logger.info("Bot is active and ready to process slash commands.")

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

    # Total channel limit safeguard to prevent long rate limits (max 50 at a time)
    if text_channels + voice_channels > 50:
        await interaction.response.send_message("❌ To prevent rate limits, you can create a maximum of 50 total channels at a time.", ephemeral=True)
        return

    # Defer the interaction as creating channels is slow and takes more than 3 seconds
    await interaction.response.defer(ephemeral=False)
    
    progress_msg = await interaction.followup.send("⏳ Initializing setup...")
    
    # Create categories if counts are greater than 0
    text_category = None
    if text_channels > 0:
        await progress_msg.edit(content="📁 Creating category: **TEXT CHANNELS**...")
        text_category = await guild.create_category(name="TEXT CHANNELS")
        
    voice_category = None
    if voice_channels > 0:
        await progress_msg.edit(content="📁 Creating category: **VOICE CHANNELS**...")
        voice_category = await guild.create_category(name="VOICE CHANNELS")
        
    # Create Text Channels
    created_text_count = 0
    for i in range(1, text_channels + 1):
        channel_name = f"text-channel-{i}"
        await progress_msg.edit(content=f"📝 Creating text channel: `{channel_name}` ({i}/{text_channels})...")
        await guild.create_text_channel(name=channel_name, category=text_category)
        created_text_count += 1
        await asyncio.sleep(0.5) # Prevent rate limits
        
    # Create Voice Channels
    created_voice_count = 0
    for i in range(1, voice_channels + 1):
        channel_name = f"Voice Channel {i}"
        await progress_msg.edit(content=f"🔊 Creating voice channel: `{channel_name}` ({i}/{voice_channels})...")
        await guild.create_voice_channel(name=channel_name, category=voice_category)
        created_voice_count += 1
        await asyncio.sleep(0.5) # Prevent rate limits
        
    await progress_msg.delete()
    
    # Send final embed summary
    embed = discord.Embed(
        title="🎉 Server Setup Completed Successfully",
        description="The requested categories and channels have been created.",
        color=discord.Color.green()
    )
    embed.add_field(
        name="📁 Categories Created", 
        value=f"• TEXT CHANNELS\n• VOICE CHANNELS" if (text_channels > 0 and voice_channels > 0) else "• Categories created.", 
        inline=False
    )
    embed.add_field(name="📝 Text Channels", value=f"Created **{created_text_count}** channel(s)", inline=True)
    embed.add_field(name="🔊 Voice Channels", value=f"Created **{created_voice_count}** channel(s)", inline=True)
    embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
    
    await interaction.followup.send(embed=embed)

# 2. /ping command
@bot.tree.command(name="ping", description="Returns the bot latency in milliseconds.")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"🏓 Pong! Latency is `{latency}ms`.")

# 3. /serverinfo command
@bot.tree.command(name="serverinfo", description="Shows information about the Discord server.")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("❌ This command can only be used within a server.", ephemeral=True)
        return
        
    # Attempt to fetch owner details
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
        title=f"ℹ️ Server Info - {guild.name}",
        color=discord.Color.blue()
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
        
    embed.add_field(name="Server Name", value=guild.name, inline=True)
    embed.add_field(name="Server ID", value=guild.id, inline=True)
    embed.add_field(name="Owner", value=owner_str, inline=False)
    embed.add_field(name="Total Members", value=guild.member_count, inline=True)
    embed.add_field(name="Total Roles", value=roles_count, inline=True)
    embed.add_field(name="Categories", value=categories, inline=True)
    embed.add_field(name="Text Channels", value=text_channels, inline=True)
    embed.add_field(name="Voice Channels", value=voice_channels, inline=True)
    
    # Format creation date
    created_at_str = guild.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    embed.add_field(name="Created At", value=created_at_str, inline=False)
    
    embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
    
    await interaction.response.send_message(embed=embed)

if __name__ == "__main__":
    token = os.getenv("TOKEN")
    if not token:
        logger.critical("Error: TOKEN environment variable is missing!")
        raise ValueError("TOKEN environment variable is missing from the environment configuration.")
    
    bot.run(token)
