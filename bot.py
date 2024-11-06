import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import asyncio
from discord.ui import Button, View
import config  

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True 

bot = commands.Bot(command_prefix="!", intents=intents)

target_channel_id = config.TARGET_CHANNEL_ID
song_queue = []
current_song_url = None
current_title = None
current_duration = None 
repeat_queue = False 

async def join_target_channel():
    """الاتصال بالغرفة المستهدفة"""
    channel = bot.get_channel(target_channel_id)
    if channel:
        if bot.voice_clients:
            if bot.voice_clients[0].channel != channel:
                await bot.voice_clients[0].disconnect() 
        if not bot.voice_clients:
            await channel.connect()

async def play_next_in_queue():
    global current_song_url, current_title, current_duration
    if repeat_queue and not song_queue:
        song_queue.extend(repeated_song_queue)

    if song_queue:
        current_song_url, current_title, current_duration = song_queue.pop(0)
        await continue_playing()
    else:
        current_song_url, current_title, current_duration = None, None, None

async def continue_playing():
    if current_song_url and bot.voice_clients:
        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -loglevel panic',
            'options': '-vn'
        }
        audio_source = discord.FFmpegPCMAudio(current_song_url, **ffmpeg_options)
        audio_source = discord.PCMVolumeTransformer(audio_source, volume=1.0)
        bot.voice_clients[0].play(
            audio_source,
            after=lambda e: asyncio.run_coroutine_threadsafe(play_next_in_queue(), bot.loop)
        )

@bot.event
async def on_ready():
    print(f"{bot.user} is online and ready to play music!")
    await join_target_channel()

@bot.command(name="play", help="Play a song from YouTube, Spotify, SoundCloud, etc.")
async def play(ctx, *, song_name):
    global current_song_url, current_title, current_duration, repeated_song_queue
    if not ctx.voice_client:
        await ctx.send(embed=discord.Embed(description="I'm not connected to the target voice channel!", color=discord.Color.red()))
        return

    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': 'True',
        'default_search': 'auto',
        'quiet': True,
        'extract_flat': 'True',
        'force_generic_extractor': True
    }

    if song_name.startswith("http"):
        ydl_opts['noplaylist'] = True
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(song_name, download=False)
                if 'entries' in info:
                    info = info['entries'][0]
                url = info['url']
                title = info.get('title', 'Unknown Title')
                duration_seconds = info.get('duration', None)
                if duration_seconds:
                    duration_seconds = int(duration_seconds)
                    minutes, seconds = divmod(duration_seconds, 60)
                    duration_str = f"{minutes:02}:{seconds:02}"
                else:
                    duration_str = "N/A"
            except Exception as e:
                await ctx.send(embed=discord.Embed(description=f"Error: Could not retrieve audio from the URL. {e}", color=discord.Color.red()))
                return
    else:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(f"ytsearch:{song_name}", download=False)
                if 'entries' not in info or not info['entries']:
                    await ctx.send(embed=discord.Embed(description="No results found for the song.", color=discord.Color.red()))
                    return
                url = info['entries'][0]['url']
                title = info['entries'][0].get('title', 'Unknown Title')
                duration_seconds = info['entries'][0].get('duration', None)
                if duration_seconds:
                    duration_seconds = int(duration_seconds)
                    minutes, seconds = divmod(duration_seconds, 60)
                    duration_str = f"{minutes:02}:{seconds:02}"
                else:
                    duration_str = "N/A"
            except Exception as e:
                await ctx.send(embed=discord.Embed(description=f"Error: Could not retrieve audio. {e}", color=discord.Color.red()))
                return

    current_song_url = url
    current_title = title
    current_duration = duration_str
    song_queue.append((url, title, duration_str))

    repeated_song_queue = list(song_queue)

    if not ctx.voice_client.is_playing():
        await continue_playing()
        await send_embed(ctx)
    else:
        await ctx.send(embed=discord.Embed(description=f"Added to queue: {title}", color=discord.Color.blue()))

async def send_embed(ctx):
    """إرسال رسالة مدمجة مع الأزرار للتحكم"""
    embed = discord.Embed(title="🎶 Now Playing", description=f"**{current_title}**", color=discord.Color.blue())
    embed.add_field(name="Duration", value=current_duration, inline=True)
    view = MusicControls()
    await ctx.send(embed=embed, view=view)

class MusicControls(View):
    def __init__(self):
        super().__init__(timeout=None)

    async def check_user_voice_channel(self, interaction):
        """يتحقق مما إذا كان المستخدم في نفس القناة الصوتية مع البوت"""
        if interaction.user.voice is None or interaction.user.voice.channel.id != target_channel_id:
            await interaction.response.send_message(embed=discord.Embed(description="You must be in the same voice channel as the bot to use this.", color=discord.Color.red()), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⏯️", style=discord.ButtonStyle.primary)
    async def pause_resume_button(self, interaction: discord.Interaction, button: Button):
        if not await self.check_user_voice_channel(interaction):
            return
        vc = interaction.guild.voice_client
        if vc.is_playing():
            vc.pause()
            await interaction.response.send_message(embed=discord.Embed(description="Paused the music.", color=discord.Color.blue()), ephemeral=True)
        elif vc.is_paused():
            vc.resume()
            await interaction.response.send_message(embed=discord.Embed(description="Resumed the music.", color=discord.Color.blue()), ephemeral=True)

    @discord.ui.button(label="🔁", style=discord.ButtonStyle.primary)
    async def repeat_button(self, interaction: discord.Interaction, button: Button):
        if not await self.check_user_voice_channel(interaction):
            return
        global repeat_queue
        repeat_queue = not repeat_queue
        status = "enabled" if repeat_queue else "disabled"
        await interaction.response.send_message(embed=discord.Embed(description=f"Repeat queue is now {status}.", color=discord.Color.blue()), ephemeral=True)

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.primary)
    async def skip_button(self, interaction: discord.Interaction, button: Button):
        if not await self.check_user_voice_channel(interaction):
            return
        if interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.stop()
            await interaction.response.send_message(embed=discord.Embed(description="Skipped the song.", color=discord.Color.blue()), ephemeral=True)

    @discord.ui.button(label="🔊", style=discord.ButtonStyle.secondary)
    async def volume_up_button(self, interaction: discord.Interaction, button: Button):
        if not await self.check_user_voice_channel(interaction):
            return
        if interaction.guild.voice_client and interaction.guild.voice_client.source:
            if isinstance(interaction.guild.voice_client.source, discord.PCMVolumeTransformer):
                volume = min(interaction.guild.voice_client.source.volume + 0.1, 2.0)
                interaction.guild.voice_client.source.volume = volume
                await interaction.response.send_message(embed=discord.Embed(description=f"Volume increased to {int(volume * 100)}%", color=discord.Color.blue()), ephemeral=True)

    @discord.ui.button(label="🔉", style=discord.ButtonStyle.secondary)
    async def volume_down_button(self, interaction: discord.Interaction, button: Button):
        if not await self.check_user_voice_channel(interaction):
            return
        if interaction.guild.voice_client and interaction.guild.voice_client.source:
            if isinstance(interaction.guild.voice_client.source, discord.PCMVolumeTransformer):
                volume = max(interaction.guild.voice_client.source.volume - 0.1, 0.0)
                interaction.guild.voice_client.source.volume = volume
                await interaction.response.send_message(embed=discord.Embed(description=f"Volume decreased to {int(volume * 100)}%", color=discord.Color.blue()), ephemeral=True)

@bot.command(name="stop", help="Stop the current song")
async def stop(ctx):
    global current_song_url, repeat_queue
    repeat_queue = False
    if ctx.voice_client:
        ctx.voice_client.stop()
        current_song_url = None
        song_queue.clear()  # تفريغ قائمة الانتظار
        await ctx.send(embed=discord.Embed(description="Stopped the music.", color=discord.Color.blue()))

@bot.command(name="skip", help="Skip the current song")
async def skip(ctx):
    global current_song_url
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send(embed=discord.Embed(description="Skipped the current song.", color=discord.Color.blue()))

@bot.command(name="repeat", help="Toggle repeat mode for the entire queue")
async def repeat(ctx):
    global repeat_queue
    repeat_queue = not repeat_queue
    status = "enabled" if repeat_queue else "disabled"
    await ctx.send(embed=discord.Embed(description=f"Repeat queue is now {status}.", color=discord.Color.blue()))


@bot.command(name="queue", help="Show the song queue")
async def queue(ctx):
    if song_queue:
        queue_text = "\n".join([title for _, title, _ in song_queue])
        await ctx.send(embed=discord.Embed(title="Songs in Queue", description=queue_text, color=discord.Color.blue()))
    else:
        await ctx.send(embed=discord.Embed(description="The queue is empty.", color=discord.Color.red()))

@bot.command(name="volume", help="Set the volume of the bot")
async def volume(ctx, volume: int):
    if ctx.voice_client and ctx.voice_client.source:
        if isinstance(ctx.voice_client.source, discord.PCMVolumeTransformer):
            ctx.voice_client.source.volume = max(0.0, min(volume / 100, 2.0))
            await ctx.send(embed=discord.Embed(description=f"Volume set to {volume}%", color=discord.Color.blue()))
        else:
            await ctx.send(embed=discord.Embed(description="Cannot adjust volume for this audio source.", color=discord.Color.red()))

@bot.command(name="leave", help="Disconnect the bot from the voice channel")
async def leave(ctx):
    await ctx.send(embed=discord.Embed(description="I cannot leave the target voice channel.", color=discord.Color.red()))

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    author_voice_state = message.author.voice
    if not author_voice_state or author_voice_state.channel.id != target_channel_id:
        return

    for command_name, aliases in config.COMMAND_ALIASES.items():
        for alias in aliases:
            if message.content.lower().startswith(alias):
                command_content = message.content[len(alias):].strip()
                command = bot.get_command(command_name)
                if command:
                    ctx = await bot.get_context(message)
                    if command_name == 'play':
                        await ctx.invoke(command, song_name=command_content)
                    elif command_name == 'volume':
                        try:
                            volume_value = int(command_content)
                            await ctx.invoke(command, volume=volume_value)
                        except ValueError:
                            await ctx.send(embed=discord.Embed(description="Please provide a valid volume level (0-200).", color=discord.Color.red()))
                    elif command_name == 'stop':
                        await ctx.invoke(command)
                    elif command_name == 'skip':
                        await ctx.invoke(command)
                    elif command_name == 'repeat':
                        await ctx.invoke(command)
                    elif command_name == 'queue':
                        await ctx.invoke(command)
                    elif command_name == 'leave':
                        await ctx.invoke(command)
                    return

    await bot.process_commands(message)

bot.run(config.TOKEN)
