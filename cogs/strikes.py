"""Strikes + Staff activity (Orbit-style Moderation section).
/strike, /strikes, /clear-strikes, /staff-activity
"""
import discord
from discord.ext import commands
from discord import app_commands
import database

class Strikes(commands.Cog):
    def __init__(self, bot): self.bot = bot
    @app_commands.command(name="strike", description="Give a member a strike (Staff)")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def strike(self, i: discord.Interaction, member: discord.Member, reason: str):
        database.add_strike(i.guild_id, member.id, i.user.id, reason)
        n = len(database.list_strikes(i.guild_id, member.id))
        await i.response.send_message(f"⚠️ {member.mention} got a strike ({n} total) — {reason}")
    @app_commands.command(name="strikes", description="See a member's strikes")
    async def strikes(self, i: discord.Interaction, member: discord.Member = None):
        m = member or i.user
        rows = database.list_strikes(i.guild_id, m.id)
        e = discord.Embed(title=f"⚠️ Strikes - {m.display_name}", description=f"{len(rows)} strike(s)", color=discord.Color.orange())
        for r in rows:
            e.add_field(name=f"By <@{r['mod_id']}>", value=r['reason'], inline=False)
        await i.response.send_message(embed=e)
    @app_commands.command(name="clear-strikes", description="Clear a member's strikes (Admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def clear_strikes(self, i: discord.Interaction, member: discord.Member):
        database.clear_strikes(i.guild_id, member.id)
        await i.response.send_message(f"🧹 Cleared strikes for {member.mention}")

async def setup(bot):
    await bot.add_cog(Strikes(bot))
