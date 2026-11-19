"""LOA - Leave of Absence (like Orbit's Leave (LOA) under Support).
Staff request leave, admins approve / deny, everyone can see who's on LOA.
Commands: /loa-request, /loa-approve, /loa-deny, /loa-list, /loa-end, /loa-status
Stored in bot.db (loa table) so it survives restarts.
"""
import discord
from discord.ext import commands
from discord import app_commands
import database

class LOA(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="loa-request", description="Request a Leave of Absence")
    @app_commands.describe(days="How many days? e.g. 7", reason="Why are you going on LOA?")
    async def loa_request(self, i: discord.Interaction, days: int, reason: str):
        database.add_loa(i.guild_id, i.user.id, days, reason)
        e = discord.Embed(title="📅 LOA Requested", color=discord.Color.gold())
        e.add_field(name="Staff", value=i.user.mention)
        e.add_field(name="Days", value=str(days))
        e.add_field(name="Reason", value=reason, inline=False)
        e.add_field(name="Status", value="⏳ Pending approval")
        await i.response.send_message(embed=e)

    @app_commands.command(name="loa-approve", description="Approve a LOA request (Admin/Staff lead)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def loa_approve(self, i: discord.Interaction, member: discord.Member):
        if database.set_loa_status(i.guild_id, member.id, "approved", i.user.id):
            await i.response.send_message(f"✅ Approved {member.mention}'s LOA.")
        else:
            await i.response.send_message(f"{member.mention} has no pending LOA.", ephemeral=True)

    @app_commands.command(name="loa-deny", description="Deny a LOA request (Admin/Staff lead)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def loa_deny(self, i: discord.Interaction, member: discord.Member, reason: str = "No reason given"):
        if database.set_loa_status(i.guild_id, member.id, "denied", i.user.id):
            await i.response.send_message(f"❌ Denied {member.mention}'s LOA — {reason}")
        else:
            await i.response.send_message(f"{member.mention} has no pending LOA.", ephemeral=True)

    @app_commands.command(name="loa-list", description="See who's on LOA / pending")
    async def loa_list(self, i: discord.Interaction):
        rows = database.list_loa(i.guild_id)
        e = discord.Embed(title="📅 Leave (LOA)", color=discord.Color.gold())
        if not rows:
            e.description = "Nobody is on LOA right now."
        for r in rows:
            e.add_field(name=f"<@{r['user_id']}> — {r['status']}", value=f"{r['days']} day(s) — {r['reason']}", inline=False)
        await i.response.send_message(embed=e)

    @app_commands.command(name="loa-end", description="End your LOA early")
    async def loa_end(self, i: discord.Interaction):
        if database.end_loa(i.guild_id, i.user.id):
            await i.response.send_message(f"👋 {i.user.mention} is back from LOA!")
        else:
            await i.response.send_message("You don't have an active LOA.", ephemeral=True)

    @app_commands.command(name="loa-status", description="Check someone's LOA status")
    async def loa_status(self, i: discord.Interaction, member: discord.Member = None):
        m = member or i.user
        row = database.get_loa(i.guild_id, m.id)
        if not row:
            await i.response.send_message(f"{m.mention} is not on LOA.", ephemeral=True); return
        await i.response.send_message(f"📅 {m.mention} — **{row['status']}**, {row['days']} day(s): {row['reason']}")

async def setup(bot):
    await bot.add_cog(LOA(bot))
