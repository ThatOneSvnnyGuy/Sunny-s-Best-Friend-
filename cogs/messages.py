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

    async def _scan_guild(self, guild, announce=False):
        """Count every message in the server's history, once, silently.
        Skips guilds already scanned (flag in settings) and never runs
        twice at once."""
        if guild.id in self._scanning:
            return
        if (database.get_settings(guild.id).get("messages_backfilled") or "0") == "1":
            return
        self._scanning.add(guild.id)
        total = 0
        channels = 0
        try:
            for ch in guild.text_channels:
                entries = []
                try:
                    async for msg in ch.history(limit=None):
                        if msg.author.bot:
                            continue
                        entries.append((msg.author.id, msg.created_at.strftime("%Y-%m-%d")))
                        total += 1
                    if entries:
                        database.record_messages_bulk(guild.id, entries)
                    channels += 1
                except Exception:
                    continue
                await asyncio.sleep(0)
            database.set_setting(guild.id, "messages_backfilled", "1")
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
