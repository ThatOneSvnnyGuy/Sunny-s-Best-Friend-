"""Giveaways + Welcome messages."""
import discord, asyncio, random, re
from discord.ext import commands
from discord import app_commands
import database

def parse_duration(s: str):
    m = re.match(r"(\d+)([smh])", s.lower())
    if not m: return None
    n, u = int(m.group(1)), m.group(2)
    return n if u == "s" else n*60 if u == "m" else n*3600

class Giveaways(commands.Cog):
    def __init__(self, bot): self.bot = bot
    @commands.Cog.listener()
    async def on_member_join(self, member):
        s = database.get_settings(member.guild.id)
        ch_id = s.get("welcome_channel_id")
        ch = member.guild.get_channel(ch_id) if ch_id else None
        if ch:
            tpl = s.get("welcome_message") or "👋 Welcome {user} to **{server}**! Open a ticket if you need help."
            await ch.send(tpl.replace("{user}", member.mention).replace("{server}", member.guild.name))
    @app_commands.command(name="giveaway", description="Start a giveaway (duration like 10m, 1h)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def giveaway(self, i: discord.Interaction, duration: str, prize: str):
        secs = parse_duration(duration)
        if not secs:
            await i.response.send_message("Duration like 10m, 1h, 30s", ephemeral=True); return
        e = discord.Embed(title=f"🎉 Giveaway: {prize}", description=f"React 🎉 to enter! Ends in {duration}", color=discord.Color.gold())
        await i.response.send_message(embed=e)
        msg = await i.original_response(); await msg.add_reaction("🎉")
        await asyncio.sleep(secs)
        msg = await i.channel.fetch_message(msg.id)
        users = [u async for u in msg.reactions[0].users() if not u.bot] if msg.reactions else []
        if users:
            winner = random.choice(users)
            await i.channel.send(f"🎉 {winner.mention} won **{prize}**!")
        else:
            await i.channel.send(f"Giveaway for **{prize}** ended - no one entered.")
    @app_commands.command(name="set-welcome", description="Set welcome channel (Admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_welcome(self, i: discord.Interaction, channel: discord.TextChannel):
        database.set_setting(i.guild_id, "welcome_channel_id", channel.id)
        await i.response.send_message(f"Welcome channel set to {channel.mention}")

async def setup(bot): await bot.add_cog(Giveaways(bot))
