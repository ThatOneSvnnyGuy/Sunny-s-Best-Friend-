"""Message counts - /messages [@user]
Shows how many messages someone sent: total, today, week, month, year.
The bot scans a server's full channel history automatically when it
joins, so /messages is truly all-time from the start - no command
needed. Live messages keep counting after that.
"""
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import database

class Messages(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._scanning = set()  # guild ids with a scan already running

    async def _scan_channel(self, guild, ch, joined):
        """Count one channel's (or thread's) pre-join history. Returns
        (messages counted, completed?). Resumes from its saved watermark.
        If fetching fails partway, completed is False so the channel is
        retried later instead of being silently dropped."""
        oldest = await asyncio.to_thread(database.get_scan_progress, guild.id, ch.id)
        if oldest == -1:
            return 0, True
        before = discord.Object(id=oldest) if oldest else None
        batch = []
        total = 0
        try:
            async for msg in ch.history(limit=None, before=before):
                if joined is not None and msg.created_at >= joined:
                    continue  # counted live already, skip
                oldest = msg.id
                if not msg.author.bot:
                    batch.append((msg.author.id, msg.created_at.strftime("%Y-%m-%d")))
                    total += 1
                if len(batch) >= 500:
                    await asyncio.to_thread(database.record_messages_bulk, guild.id, batch)
                    await asyncio.to_thread(database.set_scan_progress, guild.id, ch.id, oldest)
                    batch = []
            if batch:
                await asyncio.to_thread(database.record_messages_bulk, guild.id, batch)
                await asyncio.to_thread(database.set_scan_progress, guild.id, ch.id, oldest)
            await asyncio.to_thread(database.set_scan_progress, guild.id, ch.id, -1)
        except discord.Forbidden:
            # Bot can never read this channel (e.g. private channel) —
            # mark it done so it doesn't block the scan forever.
            await asyncio.to_thread(database.set_scan_progress, guild.id, ch.id, -1)
            return total, True
        except Exception:
            return total, False
        return total, True

    async def _channel_threads(self, ch):
        """Every thread in a channel: active ones, public archived, and
        PRIVATE archived (archived_threads only returns public ones by
        default, so private threads were being missed entirely)."""
        seen = set()
        out = []
        for t in list(getattr(ch, "threads", []) or []):
            if t.id not in seen:
                seen.add(t.id)
                out.append(t)
        for private in (False, True):
            try:
                async for t in ch.archived_threads(limit=None, private=private):
                    if t.id not in seen:
                        seen.add(t.id)
                        out.append(t)
            except Exception:
                pass
        return out

    async def _scan_guild(self, guild, announce=False):
        """Count a server's pre-join message history, silently, without
        blocking commands and without ever double-counting:
        - Only messages from BEFORE the bot joined are scanned (everything
          after that is already counted live as it arrives).
        - Covers text channels, voice-channel chats, and every thread
          (active + archived) in text and forum channels.
        - Writes happen in small batches on a worker thread, so the bot
          keeps answering commands while the scan runs.
        - A per-channel watermark is saved as it goes, so if the bot
          restarts mid-scan it resumes where it left off instead of
          starting over. Rows from any earlier partial scan are cleared
          first, so nothing gets counted twice."""
        if guild.id in self._scanning:
            return
        # Scan version 2 includes threads/forum/voice chats. A server
        # flagged "1" (text channels only) gets scanned again — the
        # per-channel watermarks skip what's already done, so only the
        # new coverage is added, nothing is re-counted.
        if (database.get_settings(guild.id).get("messages_backfilled") or "0") == "4":
            return
        self._scanning.add(guild.id)
        try:
            joined = guild.me.joined_at if guild.me else None
            # First clean scan for this guild: drop any counts left by the
            # older scan versions (they counted everything, including
            # messages already counted live, so the numbers were inflated).
            # Once the new scan has started, its watermarks exist and later
            # restarts resume instead of wiping.
            if not await asyncio.to_thread(database.has_scan_progress, guild.id):
                await asyncio.to_thread(database.clear_messages, guild.id)
            total = 0
            scanned = 0
            all_done = True
            for ch in guild.text_channels:
                n, ok = await self._scan_channel(guild, ch, joined)
                total += n
                all_done = all_done and ok
                scanned += 1
                # Threads in this channel (active + public/private archived)
                threads = await self._channel_threads(ch)
                for t in threads:
                    n, ok = await self._scan_channel(guild, t, joined)
                    total += n
                    all_done = all_done and ok
                    scanned += 1
                await asyncio.sleep(0)
            try:
                active = await guild.fetch_active_threads()
                for t in active.threads:
                    n, ok = await self._scan_channel(guild, t, joined)
                    total += n
                    all_done = all_done and ok
                    scanned += 1
            except Exception:
                pass
            for ch in guild.voice_channels:
                n, ok = await self._scan_channel(guild, ch, joined)
                total += n
                all_done = all_done and ok
                scanned += 1
                await asyncio.sleep(0)
            for ch in getattr(guild, "forum_channels", []) or []:
                threads = await self._channel_threads(ch)
                for t in threads:
                    n, ok = await self._scan_channel(guild, t, joined)
                    total += n
                    all_done = all_done and ok
                    scanned += 1
                await asyncio.sleep(0)
            if all_done:
                database.set_setting(guild.id, "messages_backfilled", "4")
                print(f"📊 History scan done for {guild.name}: {total:,} messages in {scanned} channels/threads.")
            else:
                print(f"📊 History scan partial for {guild.name}: {total:,} messages so far, some channels failed and will be retried.")
        finally:
            self._scanning.discard(guild.id)

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        # New server: scan its history right away, in the background.
        asyncio.create_task(self._scan_guild(guild))

    @commands.Cog.listener()
    async def on_ready(self):
        # Servers the bot was already in before this feature: scan any that
        # were never backfilled, once. Guilds already flagged are skipped.
        for guild in list(self.bot.guilds):
            asyncio.create_task(self._scan_guild(guild))

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild: return
        database.record_message(message.guild.id, message.author.id)

    @app_commands.command(name="messages", description="How many messages has someone sent? Total, today, week, month, year")
    @app_commands.describe(member="Who to check - leave blank for yourself")
    async def messages(self, i: discord.Interaction, member: discord.Member = None):
        member = member or i.user
        s = database.get_message_stats(i.guild_id, member.id)
        top = database.top_messages(i.guild_id, limit=100)
        rank = next((n + 1 for n, d in enumerate(top) if d["user_id"] == member.id), None)
        e = discord.Embed(
            title=f"💬 Messages - {member.display_name}",
            color=discord.Color.blurple(),
        )
        e.set_thumbnail(url=member.display_avatar.url)
        e.add_field(name="All-time", value=f"**{s['total']:,}**", inline=True)
        e.add_field(name="Today", value=f"**{s['today']:,}**", inline=True)
        e.add_field(name="This week", value=f"**{s['week']:,}**", inline=True)
        e.add_field(name="This month", value=f"**{s['month']:,}**", inline=True)
        e.add_field(name="This year", value=f"**{s['year']:,}**", inline=True)
        if rank:
            e.add_field(name="Server rank", value=f"**#{rank}**", inline=True)
        backfilled = (database.get_settings(i.guild_id).get("messages_backfilled") or "0") == "1"
        if backfilled:
            e.set_footer(text="Week = Mon-Sun (UTC) • All-time total includes full channel history.")
        else:
            e.set_footer(text="Week = Mon-Sun (UTC) • History scan still running — totals fill in as it goes.")
        await i.response.send_message(embed=e)

    @app_commands.command(name="top-messages", description="Who talks the most in this server?")
    async def top_messages(self, i: discord.Interaction):
        top = database.top_messages(i.guild_id, limit=10)
        lines = []
        for n, d in enumerate(top, 1):
            m = i.guild.get_member(d["user_id"])
            name = m.display_name if m else f"<@{d['user_id']}>"
            lines.append(f"**{n}.** {name} — **{d['n']:,}**")
        e = discord.Embed(title="🏆 Top talkers", description="\n".join(lines) or "No messages counted yet.",
                          color=discord.Color.gold())
        await i.response.send_message(embed=e)

async def setup(bot): await bot.add_cog(Messages(bot))
