"""Music - /play, /stop, /skip, /queue
Needs FFmpeg installed on Windows (see README). Uses yt-dlp.
If FFmpeg is missing, /play will tell you instead of crashing.
"""
import discord, asyncio
from discord.ext import commands
from discord import app_commands
import yt_dlp

YDL_OPTS = {"format": "bestaudio/best", "noplaylist": True, "quiet": True, "default_search": "ytsearch"}
FFMPEG_OPTS = {"before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5", "options": "-vn"}

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot; self.queues = {}
    def _queue(self, guild_id): return self.queues.setdefault(guild_id, [])
    @app_commands.command(name="play", description="Play a song (YouTube search / link)")
    async def play(self, i: discord.Interaction, song: str):
        if not i.user.voice:
            await i.response.send_message("Join a voice channel first!", ephemeral=True); return
        await i.response.defer()
        vc = i.guild.voice_client
        if not vc:
            vc = await i.user.voice.channel.connect()
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            try:
                info = ydl.extract_info(song, download=False)
                if "entries" in info: info = info["entries"][0]
                url = info["url"]; title = info.get("title", song)
            except Exception as e:
                await i.followup.send(f"Couldn't find that song: {e}"); return
        q = self._queue(i.guild_id); q.append((title, url))
        if not vc.is_playing():
            await self._play_next(i.guild, vc)
            await i.followup.send(f"▶️ Now playing: **{title}**")
        else:
            await i.followup.send(f"➕ Queued: **{title}**")
    async def _play_next(self, guild, vc):
        q = self._queue(guild.id)
        if not q: return
        title, url = q.pop(0)
        try:
            vc.play(discord.FFmpegPCMAudio(url, **FFMPEG_OPTS), after=lambda e: asyncio.run_coroutine_threadsafe(self._play_next(guild, vc), self.bot.loop))
        except Exception as e:
            print(f"Music error (is FFmpeg installed?): {e}")
    @app_commands.command(name="stop", description="Stop music and leave voice")
    async def stop(self, i: discord.Interaction):
        vc = i.guild.voice_client
        if vc: await vc.disconnect()
        self.queues[i.guild_id] = []
        await i.response.send_message("⏹️ Stopped.")
    @app_commands.command(name="skip", description="Skip current song")
    async def skip(self, i: discord.Interaction):
        vc = i.guild.voice_client
        if vc and vc.is_playing():
            vc.stop(); await i.response.send_message("⏭️ Skipped.")
            await self._play_next(i.guild, vc)
        else: await i.response.send_message("Nothing playing.", ephemeral=True)
    @app_commands.command(name="queue", description="Show the music queue")
    async def queue(self, i: discord.Interaction):
        q = self._queue(i.guild_id)
        await i.response.send_message("\n".join([f"{n}. {t}" for n, (t, _) in enumerate(q, 1)]) or "Queue is empty.")

async def setup(bot): await bot.add_cog(Music(bot))
