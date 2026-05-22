import os
import io
import base64
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
        self.muted_channels = set()

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

async def ask_gemini(prompt: str, system_instruction: str = None) -> str:
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        return "⚠️ **Gemini AI is not configured.** Please add the `GEMINI_API_KEY` variable in your Railway dashboard variables to enable chatting."
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
    headers = {"Content-Type": "application/json"}
    
    sys_inst = system_instruction or "أنت مساعد ذكاء اصطناعي محترف، جاد، ومثقف للغاية. تجيب بدقة وموضوعية بالعامية المصرية الراقية والمهذبة (مثال لأسلوبك الشات المعتاد: استخدام كلمات مثل 'يا معلم'، 'الحقيقة'، 'بص'، 'تمام'، 'كده'). تجنب تماماً أي سخرية أو قلة أدب أو مزاح غير لائق، وكن محترماً وودوداً. رتب ردودك ونظمها بشكل ممتاز ومقروء باستخدام الترقيم، النقاط، والعناوين العريضة وعلامات التنسيق (Markdown)."
    
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "system_instruction": {
            "parts": [{"text": sys_inst}]
        }
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    try:
                        candidates = data.get('candidates', [])
                        if not candidates:
                            return "⚠️ **AI Response Empty**: No response was generated (it may have been blocked by safety filters)."
                        
                        candidate = candidates[0]
                        finish_reason = candidate.get('finishReason')
                        if finish_reason and finish_reason not in ['STOP', 'MAX_TOKENS']:
                            return f"⚠️ **AI Response Blocked**: Request stopped with reason `{finish_reason}`."
                        
                        content = candidate.get('content', {})
                        parts = content.get('parts', [])
                        if not parts or 'text' not in parts[0]:
                            return "⚠️ **AI Response Error**: Could not parse text response from model."
                            
                        return parts[0]['text']
                    except Exception as parse_error:
                        logger.error(f"Failed to parse Gemini response: {parse_error}. Data: {data}")
                        return "⚠️ **Error:** Failed to parse the AI response structure."
                else:
                    err_text = await response.text()
                    logger.error(f"Gemini API returned status {response.status}: {err_text}")
                    return f"⚠️ **Error:** Failed to connect to AI server (Status {response.status}). Please check your Gemini API key."
    except Exception as e:
        logger.error(f"Error querying Gemini: {e}")
        return "⚠️ **Error:** An exception occurred while contacting the AI."

# Mention and Auto-Reply listener with Mute capability
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    content = message.content.strip()
    if not content:
        return

    # Normalize Arabic text for cleaner matching
    normalized = content.lower()
    normalized = normalized.replace('ة', 'ه').replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')

    # Mute keywords (shut up triggers)
    mute_keywords = ["اسكت", "اخرس", "اخرص", "خرس", "خرص", "عرص", "خول", "زاني", "كسمك", "ابن الشرموطه", "ابن الشرموطة", "شرموطة", "شرموطه"]
    
    should_mute = False
    for kw in mute_keywords:
        if kw in normalized:
            should_mute = True
            break

    is_mentioned = bot.user in message.mentions

    if should_mute:
        bot.muted_channels.add(message.channel.id)
        # Edit-style feedback
        status_msg = await message.reply("⚙️ جاري معالجة الطلب وصيانة النظام...")
        response = await ask_gemini("صاحب الرسالة شتمني وقالي اسكت. رد عليه بالعامية المصرية بأسلوب مهذب ومحترف وجاد جداً وقوله انك هتسكت ومش هترد تاني غير لو عملك منشن.")
        await status_msg.edit(content=response)
        return

    # Unmute checks
    is_unmute = "اتكلم" in normalized or "انطق" in normalized or "اتكلم يا خول" in normalized
    if is_unmute or is_mentioned:
        if message.channel.id in bot.muted_channels:
            bot.muted_channels.discard(message.channel.id)

    is_muted = message.channel.id in bot.muted_channels

    # Respond to all messages if the channel is NOT muted, or respond to mentions if muted
    if is_mentioned or not is_muted:
        # Strip the mention of the bot
        clean_content = content.replace(f"<@!{bot.user.id}>", "").replace(f"<@{bot.user.id}>", "").strip()
        
        # If it was a mention but content is empty
        if is_mentioned and not clean_content:
            status_msg = await message.reply("🔍 جاري البحث والاستعلام...")
            response = await ask_gemini("رد باللغة العربية الفصحى وقوله مرحباً، أنا جاهز لمساعدتك. كيف يمكنني إفادتك اليوم؟")
            await status_msg.edit(content=response)
            return

        prompt = clean_content if clean_content else content
        
        # Immediate placeholder response for extreme speed feeling
        status_msg = await message.reply("🔍 جاري البحث والاستعلام...")
        response = await ask_gemini(prompt)
        if len(response) > 2000:
            response = response[:1990] + "..."
        await status_msg.edit(content=response)

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
    await interaction.response.send_message("🔍 جاري البحث والاستعلام...")
    response = await ask_gemini(message)
    if len(response) > 2000:
        response = response[:1990] + "..."
    await interaction.edit_original_response(content=response)

# 4. /roast command (Sarcastic AI Roast)
@bot.tree.command(name="roast", description="Gently roasts a member of the server using AI.")
@app_commands.describe(user="The member you want to roast")
async def roast(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.send_message("🔥 جاري تحضير القصف...")
    prompt = f"Write a highly sarcastic, witty, and savage roast for a Discord user named {user.display_name}. Speak directly to them, keep it sharp, funny, and concise."
    response = await ask_gemini(prompt, system_instruction="أنت بوت ديسكورد مصري ساخر، رد بالعامية المصرية بأسلوب قصف جبهة كوميدي وسلس ومضحك للغاية للشخص المحدد.")
    if len(response) > 2000:
        response = response[:1990] + "..."
    await interaction.edit_original_response(content=f"{user.mention} {response}")

# /imagine command — AI Image Generation via Gemini
@bot.tree.command(name="imagine", description="يولد صورة بالذكاء الاصطناعي بناءً على وصفك.")
@app_commands.describe(prompt="وصف الصورة اللي عايزها بالعربي أو الانجليزي")
async def imagine(interaction: discord.Interaction, prompt: str):
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        await interaction.response.send_message("❌ مفتاح الـ API مش موجود. أضف `GEMINI_API_KEY` في المتغيرات.", ephemeral=True)
        return

    await interaction.response.send_message("🎨 جاري توليد الصورة، استنى ثواني...")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent?key={gemini_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"role": "user", "parts": [{"text": f"Generate a high quality, detailed image of: {prompt}"}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE"]
        }
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    try:
                        candidates = data.get("candidates", [])
                        if not candidates:
                            await interaction.edit_original_response(content="⚠️ الذكاء الاصطناعي ما قدرش يولد الصورة دي (ممكن محتوى مرفوض).")
                            return

                        parts = candidates[0].get("content", {}).get("parts", [])
                        image_part = None
                        for part in parts:
                            if "inlineData" in part:
                                image_part = part["inlineData"]
                                break

                        if not image_part:
                            await interaction.edit_original_response(content="⚠️ الاستجابة ما فيهاش صورة. جرب وصف تاني.")
                            return

                        image_bytes = base64.b64decode(image_part["data"])
                        mime = image_part.get("mimeType", "image/png")
                        ext = "jpg" if "jpeg" in mime else "png"
                        file = discord.File(fp=io.BytesIO(image_bytes), filename=f"imagine.{ext}")

                        embed = discord.Embed(
                            title="🎨 الصورة المولّدة",
                            description=f"**الوصف:** {prompt}",
                            color=discord.Color.from_rgb(0, 0, 0)
                        )
                        embed.set_image(url=f"attachment://imagine.{ext}")
                        embed.set_footer(text=f"طلب بواسطة {interaction.user.name}", icon_url=interaction.user.display_avatar.url)

                        await interaction.edit_original_response(content=None, attachments=[file], embed=embed)

                    except Exception as parse_err:
                        logger.error(f"Image parse error: {parse_err}")
                        await interaction.edit_original_response(content="❌ حصل خطأ في معالجة الصورة.")
                elif resp.status == 429:
                    await interaction.edit_original_response(content="⏳ تجاوزت الحد المسموح من الطلبات. استنى دقيقة وجرب تاني.")
                else:
                    err = await resp.text()
                    logger.error(f"Image generation failed: {resp.status} — {err}")
                    await interaction.edit_original_response(content=f"❌ فشل توليد الصورة (Status {resp.status}).")
    except Exception as e:
        logger.error(f"Error in /imagine: {e}")
        await interaction.edit_original_response(content="❌ حصل استثناء أثناء التواصل مع الـ API.")

# 5. /clear command (Advanced Message Purge - Admin only)
@bot.tree.command(name="clear", description="Deletes messages in the channel with optional user and keyword filters (Admin only).")
@app_commands.describe(
    amount="Number of messages to scan and delete",
    user="Only delete messages from this specific member",
    keyword="Only delete messages containing this specific keyword"
)
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.default_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, amount: int, user: discord.Member = None, keyword: str = None):
    if amount < 1:
        await interaction.response.send_message("❌ Amount must be at least 1.", ephemeral=True)
        return
        
    amount = min(amount, 500)
    await interaction.response.defer(ephemeral=True)
    
    def check_msg(msg):
        if user and msg.author.id != user.id:
            return False
        if keyword and keyword.lower() not in msg.content.lower():
            return False
        return True

    try:
        deleted = await interaction.channel.purge(limit=amount, check=check_msg)
        filter_info = ""
        if user:
            filter_info += f" from {user.mention}"
        if keyword:
            filter_info += f" containing `{keyword}`"
            
        embed = discord.Embed(
            description=f"✦ Successfully deleted **{len(deleted)}** messages{filter_info}.",
            color=discord.Color.from_rgb(0, 0, 0)
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        logger.error(f"Purge failed: {e}")
        await interaction.followup.send(f"❌ Failed to delete messages: {str(e)}", ephemeral=True)

# 6. /search command (Message Search - Admin only)
@bot.tree.command(name="search", description="Searches the channel for messages matching a query.")
@app_commands.describe(
    query="The word or phrase to search for",
    channel="The channel to search in (defaults to current)",
    limit="Max number of messages to scan (default 100, max 1000)"
)
async def search(interaction: discord.Interaction, query: str, channel: discord.TextChannel = None, limit: int = 100):
    search_channel = channel or interaction.channel
    limit = min(max(limit, 1), 1000)
    
    await interaction.response.defer(ephemeral=False)
    progress_msg = await interaction.followup.send(f"⏳ Scanning up to {limit} messages in {search_channel.mention}...")
    
    results = []
    try:
        async for msg in search_channel.history(limit=limit):
            if query.lower() in msg.content.lower() and not msg.author.bot:
                results.append(msg)
    except Exception as e:
        logger.error(f"Search failed: {e}")
        await progress_msg.edit(content=f"❌ Failed to read message history: {str(e)}")
        return

    await progress_msg.delete()
    
    if not results:
        embed = discord.Embed(
            description=f"✦ No messages matching `{query}` were found in {search_channel.mention}.",
            color=discord.Color.from_rgb(0, 0, 0)
        )
        await interaction.followup.send(embed=embed)
        return
        
    # If too many results, send as txt attachment
    if len(results) > 10:
        file_content = f"Search results for '{query}' in #{search_channel.name} (Total matches: {len(results)}):\n\n"
        for idx, msg in enumerate(results, 1):
            time_str = msg.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')
            file_content += f"[{idx}] {msg.author} ({time_str}):\n{msg.content}\n{'-'*40}\n"
            
        import io
        file_data = io.BytesIO(file_content.encode('utf-8'))
        file = discord.File(fp=file_data, filename=f"search_results_{search_channel.name}.txt")
        
        embed = discord.Embed(
            title="✦ Search Results",
            description=f"Found **{len(results)}** messages matching `{query}`. Results are packaged in the attached text file.",
            color=discord.Color.from_rgb(0, 0, 0)
        )
        await interaction.followup.send(embed=embed, file=file)
    else:
        embed = discord.Embed(
            title="✦ Search Results",
            description=f"Found **{len(results)}** messages matching `{query}` in {search_channel.mention}:",
            color=discord.Color.from_rgb(0, 0, 0)
        )
        for idx, msg in enumerate(results, 1):
            time_str = msg.created_at.strftime('%m/%d %H:%M')
            content_snippet = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
            embed.add_field(
                name=f"{idx}. {msg.author.name} ({time_str})",
                value=content_snippet,
                inline=False
            )
        await interaction.followup.send(embed=embed)

# 6. /avatar command (Show profile picture)
@bot.tree.command(name="avatar", description="Displays a user's avatar in high quality.")
@app_commands.describe(user="The member whose avatar you want to view")
async def avatar(interaction: discord.Interaction, user: discord.Member = None):
    target_user = user or interaction.user
    embed = discord.Embed(
        title=f"✦ {target_user.name}'s Avatar",
        color=discord.Color.from_rgb(0, 0, 0)
    )
    embed.set_image(url=target_user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

# 7. /userinfo command (Show member details)
@bot.tree.command(name="userinfo", description="Displays detailed information about a member.")
@app_commands.describe(user="The member to get information about")
async def userinfo(interaction: discord.Interaction, user: discord.Member = None):
    target_user = user or interaction.user
    
    roles = [role.mention for role in target_user.roles[1:]] # Exclude @everyone
    roles_str = ", ".join(roles) if roles else "None"
    
    embed = discord.Embed(
        title=f"✦ User Info - {target_user.name}",
        color=discord.Color.from_rgb(0, 0, 0)
    )
    embed.set_thumbnail(url=target_user.display_avatar.url)
    
    embed.add_field(name="◼ Account Info", value=f"**Username:** {target_user.name}\n**ID:** {target_user.id}\n**Bot:** {'Yes' if target_user.bot else 'No'}", inline=False)
    embed.add_field(name="◼ Guild Info", value=f"**Joined Guild:** {target_user.joined_at.strftime('%Y-%m-%d %H:%M:%S UTC') if target_user.joined_at else 'Unknown'}\n**Created Account:** {target_user.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}", inline=False)
    embed.add_field(name="◼ Roles", value=roles_str, inline=False)
    
    await interaction.response.send_message(embed=embed)

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
